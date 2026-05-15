#!/usr/bin/env bash
set -u

# Continuous LiteLLM stress test with 3 concurrent simulated users.
#
# Required:
#   export LITELLM_API_KEY='sk-...'
#
# Optional:
#   LITELLM_URL='http://192.168.0.20:4000'
#   MODEL='Qwen3.6-35B-A3B'
#   USERS=3
#   DURATION_SECONDS=60      # 0 = run until Ctrl+C
#   SLEEP_SECONDS=0          # pause between requests per user
#   OUTPUT_MODE=short        # short = bounded words, long = long completions
#   MIN_WORDS=600
#   MAX_WORDS=800
#   MAX_TOKENS=1200          # output budget per request
#   OUTPUT_TARGET_TOKENS=2000
#   PROMPT_REPEAT=1          # keep 1-2 to stay roughly in 100-1000 input tokens
#   REQUEST_TIMEOUT_SECONDS=120
#   OUT_DIR='./stress_results'

if [ -z "${LITELLM_API_KEY:-}" ]; then
  echo "Missing LITELLM_API_KEY. Run: export LITELLM_API_KEY='sk-...'" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to collect token usage stats." >&2
  exit 1
fi

LITELLM_URL="${LITELLM_URL:-http://192.168.0.20:4000}"
LITELLM_URL="${LITELLM_URL%/}"
MODEL="${MODEL:-Qwen3.6-35B-A3B}"
USERS="${USERS:-3}"
DURATION_SECONDS="${DURATION_SECONDS:-0}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0}"
OUTPUT_MODE="${OUTPUT_MODE:-short}"
MIN_WORDS="${MIN_WORDS:-600}"
MAX_WORDS="${MAX_WORDS:-800}"
if [ -z "${MAX_TOKENS+x}" ]; then
  if [ "$OUTPUT_MODE" = "long" ]; then
    MAX_TOKENS=2000
  else
    MAX_TOKENS=1200
  fi
fi
OUTPUT_TARGET_TOKENS="${OUTPUT_TARGET_TOKENS:-2000}"
PROMPT_REPEAT="${PROMPT_REPEAT:-1}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-120}"
OUT_DIR="${OUT_DIR:-./stress_results_$(date +%Y%m%d_%H%M%S)}"

if [ "$PROMPT_REPEAT" -gt 2 ]; then
  echo "PROMPT_REPEAT=$PROMPT_REPEAT would likely exceed 1000 input tokens; clamping to 2." >&2
  PROMPT_REPEAT=2
fi

mkdir -p "$OUT_DIR"

PIDS=""
TEST_STARTED_EPOCH="$(date +%s)"

summary() {
  echo
  echo "Summary"
  echo "Results directory: $OUT_DIR"
  now_epoch="$(date +%s)"
  elapsed_seconds=$((now_epoch - TEST_STARTED_EPOCH))
  if [ "$elapsed_seconds" -le 0 ]; then
    elapsed_seconds=1
  fi

  awk -F, -v elapsed="$elapsed_seconds" '
    FNR == 1 { next }
    {
      total += 1
      if ($5 ~ /^2/) {
        ok += 1
        user_ok[$2] += 1
      } else {
        failed += 1
        user_failed[$2] += 1
      }
      if ($6 != "") {
        latency += $6
        latency_count += 1
        if ($6 > max_latency) {
          max_latency = $6
        }
      }
      prompt_tokens += $7
      completion_tokens += $8
      total_tokens += $9
      if ($10 != "") {
        completion_tps_sum += $10
        completion_tps_count += 1
      }
      if ($11 != "") {
        total_tps_sum += $11
        total_tps_count += 1
      }
      user_prompt[$2] += $7
      user_completion[$2] += $8
      user_total[$2] += $9
      seen_user[$2] = 1
    }
    END {
      avg_latency = latency_count ? latency / latency_count : 0
      avg_completion_tps = completion_tps_count ? completion_tps_sum / completion_tps_count : 0
      avg_total_tps = total_tps_count ? total_tps_sum / total_tps_count : 0
      weighted_completion_tps = latency > 0 ? completion_tokens / latency : 0
      weighted_total_tps = latency > 0 ? total_tokens / latency : 0
      wall_completion_tps = completion_tokens / elapsed
      wall_total_tps = total_tokens / elapsed
      avg_completion_tokens_per_request = ok ? completion_tokens / ok : 0

      printf "elapsed_seconds=%d\n", elapsed
      printf "total_requests=%d success=%d failed=%d\n", total, ok, failed
      printf "prompt_tokens=%d completion_tokens=%d total_tokens=%d\n", prompt_tokens, completion_tokens, total_tokens
      printf "avg_completion_tokens_per_successful_request=%.2f\n", avg_completion_tokens_per_request
      printf "avg_latency=%.3fs max_latency=%.3fs\n", avg_latency, max_latency
      printf "avg_completion_tokens_per_second_per_request=%.3f\n", avg_completion_tps
      printf "avg_total_tokens_per_second_per_request=%.3f\n", avg_total_tps
      printf "weighted_completion_tokens_per_second=%.3f\n", weighted_completion_tps
      printf "weighted_total_tokens_per_second=%.3f\n", weighted_total_tps
      printf "wall_completion_tokens_per_second=%.3f\n", wall_completion_tps
      printf "wall_total_tokens_per_second=%.3f\n", wall_total_tps

      print ""
      print "Per-user summary"
      for (user in seen_user) {
        printf "%s success=%d failed=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d\n", user, user_ok[user], user_failed[user], user_prompt[user], user_completion[user], user_total[user]
      }
    }
  ' "$OUT_DIR"/user_*.csv 2>/dev/null || true
}

cleanup() {
  echo
  echo "Stopping workers..."
  for pid in $PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  summary
  exit 0
}

trap cleanup INT TERM

run_user() {
  user_number="$1"
  metrics_file="$OUT_DIR/user_${user_number}.csv"
  response_file="$OUT_DIR/user_${user_number}_last_response.json"
  request_count=0
  start_epoch="$(date +%s)"

  echo "timestamp,user,request,curl_exit,http_code,time_total,prompt_tokens,completion_tokens,total_tokens,completion_tokens_per_second,total_tokens_per_second" > "$metrics_file"

  while :; do
    now_epoch="$(date +%s)"
    if [ "$DURATION_SECONDS" -gt 0 ] && [ $((now_epoch - start_epoch)) -ge "$DURATION_SECONDS" ]; then
      break
    fi

    request_count=$((request_count + 1))
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    prompt_variant=$(( (request_count + user_number) % 6 ))

    case "$prompt_variant" in
      0)
        scenario="Scrivi una review architetturale di un gateway LiteLLM davanti a un modello locale compatibile OpenAI. Valuta concorrenza, code, timeout, gestione errori, isolamento tra utenti, osservabilita, metriche di token usage e impatto della KV cache. Inserisci esempi concreti di problemi che potrebbero emergere durante un test con tre utenti simultanei."
        ;;
      1)
        scenario="Prepara un runbook operativo per investigare un degrado prestazionale in produzione. Il sistema usa LiteLLM come proxy, un backend llama.cpp su rete locale e un modello chiamato ${MODEL}. Descrivi controlli su health endpoint, log, codici HTTP, saturazione GPU, memoria, throughput token/s, retry e rate limit."
        ;;
      2)
        scenario="Crea una policy tecnica per usare guardrails in un ambiente aziendale. Confronta controlli pre_call, during_call e post_call, spiega quando bloccare, quando mascherare, quando fare solo logging, e come misurare falsi positivi, falsi negativi, latenza aggiunta e impatto sull esperienza utente."
        ;;
      3)
        scenario="Analizza un benchmark con tre utenti concorrenti che inviano prompt medi e richiedono output lunghi. Spiega come interpretare prompt_tokens, completion_tokens, total_tokens, latenza media, latenza massima, completion token per secondo e throughput aggregato nel tempo di parete."
        ;;
      4)
        scenario="Scrivi una valutazione dei rischi per un assistente interno che accede a strumenti e knowledge base. Considera prompt injection, data leakage, allucinazioni, permessi MCP, separazione dei tenant, logging sicuro, rotazione chiavi API e fallback quando un modello locale non risponde."
        ;;
      *)
        scenario="Progetta un piano di capacity planning per servire un modello locale tramite LiteLLM. Includi ipotesi di carico, dimensionamento del contesto, scelta di max_tokens, impatto dei prompt lunghi, parallelismo, continuous batching, metriche da raccogliere e criteri per dichiarare il test riuscito."
        ;;
    esac

    if [ "$OUTPUT_MODE" = "long" ]; then
      system_prompt="Rispondi in italiano. Non essere conciso: quando l utente chiede una risposta lunga, usa quasi tutto il budget di token disponibile. Segui esattamente la struttura richiesta."
      output_constraints="- Devi produrre una risposta lunga, densa e strutturata.
- Mira a usare quasi tutto il budget disponibile, circa ${OUTPUT_TARGET_TOKENS} token di completamento.
- Non rispondere in modo breve e non fermarti dopo poche frasi.
- Scrivi 12 sezioni numerate, ognuna con 2 paragrafi corposi.
- Ogni sezione deve aggiungere dettagli nuovi, senza ripetere la stessa frase.
- Mantieni l italiano tecnico, chiaro e operativo.
- Non dire che non puoi sapere i dati reali: quando servono metriche, descrivi come leggerle dal benchmark.
- Concludi solo dopo aver coperto tutti i punti richiesti."
      prompt_objective="output lungo, utile per misurare generazione sostenuta e token/s"
    else
      system_prompt="Rispondi in italiano. Devi produrre almeno ${MIN_WORDS} parole e non superare ${MAX_WORDS} parole. Non fermarti prima del minimo richiesto."
      output_constraints="- Rispondi con almeno ${MIN_WORDS} parole.
- Non superare ${MAX_WORDS} parole.
- Usa sezioni brevi e paragrafi chiari.
- Non aggiungere preamboli inutili.
- Mantieni il contenuto tecnico e concreto.
- Se servono metriche, nomina solo quelle che lo script misura."
      prompt_objective="output medio di almeno ${MIN_WORDS} parole, utile per misurare la latenza per messaggio"
    fi

    prompt_text="Stress test: utente ${user_number}, richiesta ${request_count}.

Scenario:
${scenario}

Vincoli di output:
${output_constraints}"

    prompt_block="

Contesto extra per rendere la richiesta realistica:
- Proxy: LiteLLM.
- Modello pubblico: ${MODEL}.
- Utenti concorrenti simulati: ${USERS}.
- Obiettivo: ${prompt_objective}.
- Non includere codice a meno che sia strettamente necessario."

    repeat_index=1
    while [ "$repeat_index" -le "$PROMPT_REPEAT" ]; do
      prompt_text="${prompt_text}${prompt_block}"
      repeat_index=$((repeat_index + 1))
    done

    prompt_chars="${#prompt_text}"

    payload='{
      "model": "'"$MODEL"'",
      "messages": [
        {
          "role": "system",
          "content": '"$(jq -Rs . <<< "$system_prompt")"'
        },
        {
          "role": "user",
          "content": '"$(jq -Rs . <<< "$prompt_text")"'
        }
      ],
      "user": "stress-user-'"$user_number"'",
      "temperature": 0.2,
      "max_tokens": '"$MAX_TOKENS"'
    }'

    curl_result="$(
      curl -sS \
        --max-time "$REQUEST_TIMEOUT_SECONDS" \
        -o "$response_file" \
        -w "%{http_code},%{time_total}" \
        "$LITELLM_URL/v1/chat/completions" \
        -H "Authorization: Bearer $LITELLM_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$payload"
    )"
    curl_exit="$?"

    if [ "$curl_exit" -eq 0 ]; then
      http_code="${curl_result%%,*}"
      time_total="${curl_result#*,}"
    else
      http_code="curl_error"
      time_total=""
    fi

    prompt_tokens=0
    completion_tokens=0
    total_tokens=0
    completion_tokens_per_second=""
    total_tokens_per_second=""

    if [ "$curl_exit" -eq 0 ] && [[ "$http_code" =~ ^2 ]]; then
      usage_csv="$(
        jq -r '
          [
            (.usage.prompt_tokens // 0),
            (.usage.completion_tokens // 0),
            (.usage.total_tokens // ((.usage.prompt_tokens // 0) + (.usage.completion_tokens // 0)))
          ] | @csv
        ' "$response_file" 2>/dev/null || printf '0,0,0'
      )"
      IFS=, read -r prompt_tokens completion_tokens total_tokens <<< "$usage_csv"

      if [ -n "$time_total" ]; then
        completion_tokens_per_second="$(
          awk -v tokens="$completion_tokens" -v seconds="$time_total" 'BEGIN { if (seconds > 0) printf "%.3f", tokens / seconds }'
        )"
        total_tokens_per_second="$(
          awk -v tokens="$total_tokens" -v seconds="$time_total" 'BEGIN { if (seconds > 0) printf "%.3f", tokens / seconds }'
        )"
      fi
    fi

    echo "$timestamp,stress-user-$user_number,$request_count,$curl_exit,$http_code,$time_total,$prompt_tokens,$completion_tokens,$total_tokens,$completion_tokens_per_second,$total_tokens_per_second" >> "$metrics_file"
    printf '[stress-user-%s] request=%s chars=%s curl_exit=%s http=%s time=%ss prompt_tokens=%s completion_tokens=%s total_tokens=%s completion_tps=%s\n' \
      "$user_number" "$request_count" "$prompt_chars" "$curl_exit" "$http_code" "$time_total" "$prompt_tokens" "$completion_tokens" "$total_tokens" "$completion_tokens_per_second"

    if [ "$SLEEP_SECONDS" != "0" ]; then
      sleep "$SLEEP_SECONDS"
    fi
  done
}

echo "Starting LiteLLM stress test"
echo "URL: $LITELLM_URL"
echo "Model: $MODEL"
echo "Users: $USERS"
echo "Duration seconds: $DURATION_SECONDS (0 means until Ctrl+C)"
echo "Output mode: $OUTPUT_MODE"
echo "Min words: $MIN_WORDS"
echo "Max words: $MAX_WORDS"
echo "Max tokens: $MAX_TOKENS"
echo "Prompt repeat: $PROMPT_REPEAT"
echo "Output: $OUT_DIR"
echo

user_number=1
while [ "$user_number" -le "$USERS" ]; do
  run_user "$user_number" &
  PIDS="$PIDS $!"
  user_number=$((user_number + 1))
done

wait
summary
