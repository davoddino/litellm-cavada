export const ASSIGN_BUDGET_CURL_COMMAND = `
curl -X POST --location '<your_proxy_base_url>/project/update' \\

-H 'Authorization: Bearer <your-master-key>' \\

-H 'Content-Type: application/json' \\

-d '{
  "company_id": "<COMPANY_ID>",
  "project_id": "<PROJECT_ID>",
  "budget_id": "<BUDGET_ID>"
}'

`;

export const CHAT_COMPLETIONS_CURL_COMMAND = `
curl -X POST --location '<your_proxy_base_url>/chat/completions' \\

-H 'Authorization: Bearer <server-api-key-for-project>' \\

-H 'Content-Type: application/json' \\

-d '{
  "model": "gpt-3.5-turbo",
  "messages":[{"role": "user", "content": "Hey, how's it going?"}]
}'

`;

export const OPENAI_SDK_PYTHON_CODE = `from openai import OpenAI
client = OpenAI(
  base_url="<your_proxy_base_url>",
  api_key="<server-api-key-for-project>"
)

completion = client.chat.completions.create(
  model="gpt-3.5-turbo",
  messages=[
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ]
)

print(completion.choices[0].message)`;
