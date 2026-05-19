"use client";

import { InfoCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, InputNumber, Select, Space, Switch, Tooltip, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { createCavadaLabsResource, listCavadaLabsResource, patchCavadaLabsResource } from "./api";
import type { CavadaLabsRecord } from "./types";

const KEY_MODEL_BUCKETS = ["small", "medium", "large", "advanced"] as const;
const ENDPOINT_OPTIONS = [
  { label: "Chat", value: "chat_completion" },
  { label: "Text", value: "text_completion" },
  { label: "Transcription", value: "transcription" },
  { label: "Embedding", value: "embedding" },
];
const PROVIDER_OPTIONS = ["cavadalabs", "openai", "anthropic", "azure", "gemini", "mistral", "custom"].map(
  (value) => ({ label: value, value }),
);

export interface KeyModelRoutingDraft {
  policy_id?: string;
  key_id?: string | null;
  project_id?: string;
  endpoint_type: string;
  model_bucket: string;
  model_alias: string;
  provider: string;
  priority: number;
  enabled: boolean;
  fallback_enabled: boolean;
}

interface KeyModelRoutingEditorProps {
  accessToken: string | null;
  projectId: string | null;
  keyId?: string | null;
  availableModels: string[];
  value: KeyModelRoutingDraft[];
  onChange: (value: KeyModelRoutingDraft[]) => void;
  disabled?: boolean;
}

const normalizePolicy = (policy: CavadaLabsRecord): KeyModelRoutingDraft => ({
  policy_id: typeof policy.policy_id === "string" ? policy.policy_id : undefined,
  key_id: typeof policy.key_id === "string" ? policy.key_id : null,
  project_id: typeof policy.project_id === "string" ? policy.project_id : undefined,
  endpoint_type: typeof policy.endpoint_type === "string" ? policy.endpoint_type : "chat_completion",
  model_bucket: typeof policy.model_bucket === "string" ? policy.model_bucket : "medium",
  model_alias: typeof policy.model_alias === "string" ? policy.model_alias : "",
  provider: typeof policy.provider === "string" ? policy.provider : "cavadalabs",
  priority: Number.isFinite(Number(policy.priority)) ? Number(policy.priority) : 1,
  enabled: policy.enabled !== false,
  fallback_enabled: policy.fallback_enabled !== false,
});

const nextPriorityForBucket = (policies: KeyModelRoutingDraft[], bucket: string): number => {
  const priorities = policies.filter((policy) => policy.model_bucket === bucket).map((policy) => policy.priority || 0);
  return Math.max(0, ...priorities) + 1;
};

export const extractKeyModelRoutingRows = (payload: any): KeyModelRoutingDraft[] => {
  const rows: CavadaLabsRecord[] = Array.isArray(payload?.model_policies)
    ? payload.model_policies
    : Array.isArray(payload)
      ? payload
      : [];
  return rows
    .map(normalizePolicy)
    .sort(
      (a: KeyModelRoutingDraft, b: KeyModelRoutingDraft) =>
        a.model_bucket.localeCompare(b.model_bucket) || a.priority - b.priority,
    );
};

export const collectKeyModelRoutingModels = (policies: KeyModelRoutingDraft[]): string[] => {
  const models = new Set<string>();
  policies.forEach((policy) => {
    const modelAlias = policy.model_alias.trim();
    const modelBucket = policy.model_bucket.trim();
    if (!policy.enabled || !modelAlias || !modelBucket) return;
    models.add(modelBucket);
    models.add(modelAlias);
  });
  return Array.from(models);
};

export const mergeKeyModelRoutingModels = (models: any, routingModels: string[]): string[] | undefined => {
  const existing = Array.isArray(models) ? models.filter((model) => typeof model === "string" && model.trim()) : [];
  const merged = Array.from(new Set([...existing, ...routingModels]));
  return merged.length > 0 ? merged : undefined;
};

export const getKeyModelRoutingKeyId = (keyData: CavadaLabsRecord | null | undefined): string | null => {
  const value = keyData?.token_id ?? keyData?.token;
  return typeof value === "string" && value.trim() ? value : null;
};

export const syncKeyModelRoutingPolicies = async ({
  accessToken,
  projectId,
  keyId,
  policies,
}: {
  accessToken: string | null;
  projectId: string | null;
  keyId: string | null;
  policies: KeyModelRoutingDraft[];
}): Promise<void> => {
  const cleanPolicies = policies.filter((policy) => policy.model_alias.trim() && policy.model_bucket.trim());
  if (cleanPolicies.length === 0) return;
  if (!projectId || !keyId) {
    throw new Error("Project and key are required before saving model routing priorities");
  }

  await Promise.all(
    cleanPolicies.map((policy) => {
      const body = {
        key_id: keyId,
        endpoint_type: policy.endpoint_type || "chat_completion",
        model_bucket: policy.model_bucket.trim().toLowerCase(),
        model_alias: policy.model_alias.trim(),
        provider: policy.provider || "cavadalabs",
        priority: Number(policy.priority) || 1,
        enabled: policy.enabled,
        fallback_enabled: policy.fallback_enabled,
      };
      if (policy.policy_id) {
        return patchCavadaLabsResource(accessToken, `/cavadalabs/model-policies/${policy.policy_id}`, body);
      }
      return createCavadaLabsResource(accessToken, "/cavadalabs/model-policies", {
        ...body,
        project_id: projectId,
      });
    }),
  );
};

export function KeyModelRoutingEditor({
  accessToken,
  projectId,
  keyId,
  availableModels,
  value,
  onChange,
  disabled = false,
}: KeyModelRoutingEditorProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const modelOptions = useMemo(() => {
    const selectedModels = value.map((policy) => policy.model_alias).filter(Boolean);
    return Array.from(new Set([...availableModels, ...selectedModels])).map((model) => ({
      label: model,
      value: model,
    }));
  }, [availableModels, value]);

  useEffect(() => {
    let cancelled = false;
    if (!accessToken || !projectId || !keyId) return;

    const loadPolicies = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await listCavadaLabsResource(accessToken, "/cavadalabs/model-policies", {
          project_id: projectId,
          key_id: keyId,
        });
        if (!cancelled) onChange(extractKeyModelRoutingRows(response));
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "Unable to load model routing priorities");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    loadPolicies();
    return () => {
      cancelled = true;
    };
  }, [accessToken, projectId, keyId]);

  const updatePolicy = (index: number, patch: Partial<KeyModelRoutingDraft>) => {
    onChange(value.map((policy, idx) => (idx === index ? { ...policy, ...patch } : policy)));
  };

  const addPolicy = (bucket: string) => {
    onChange([
      ...value,
      {
        endpoint_type: "chat_completion",
        model_bucket: bucket,
        model_alias: "",
        provider: "cavadalabs",
        priority: nextPriorityForBucket(value, bucket),
        enabled: true,
        fallback_enabled: true,
      },
    ]);
  };

  const removeUnsavedPolicy = (index: number) => {
    onChange(value.filter((_, idx) => idx !== index));
  };

  return (
    <Card
      size="small"
      className="mb-4"
      title={
        <Space size={6}>
          <span>Model routing priorities</span>
          <Tooltip title="Define per-key bucket aliases such as small, medium, large, and advanced. Lower priority runs first.">
            <InfoCircleOutlined />
          </Tooltip>
        </Space>
      }
      loading={isLoading}
    >
      {!projectId && <Alert type="info" showIcon message="Select a Project before configuring model routing." />}
      {error && <Alert className="mb-3" type="error" showIcon message={error} />}
      <Space direction="vertical" size={12} className="w-full">
        {KEY_MODEL_BUCKETS.map((bucket) => {
          const rows = value
            .map((policy, index) => ({ policy, index }))
            .filter((item) => item.policy.model_bucket === bucket);
          return (
            <div key={bucket} className="rounded-md border border-gray-200 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <Typography.Text strong>{bucket}</Typography.Text>
                <Button
                  size="small"
                  onClick={() => addPolicy(bucket)}
                  disabled={disabled || !projectId}
                  aria-label={`Add ${bucket} model route`}
                >
                  Add model
                </Button>
              </div>
              {rows.length === 0 ? (
                <Typography.Text type="secondary">No models configured</Typography.Text>
              ) : (
                <Space direction="vertical" size={8} className="w-full">
                  {rows.map(({ policy, index }) => (
                    <Space key={`${policy.policy_id || "draft"}-${index}`} wrap className="w-full">
                      <Select
                        showSearch
                        allowClear
                        disabled={disabled}
                        placeholder="Model"
                        style={{ minWidth: 240 }}
                        options={modelOptions}
                        value={policy.model_alias || undefined}
                        onChange={(modelAlias) => updatePolicy(index, { model_alias: modelAlias || "" })}
                      />
                      <Select
                        disabled={disabled}
                        style={{ width: 150 }}
                        options={ENDPOINT_OPTIONS}
                        value={policy.endpoint_type}
                        onChange={(endpointType) => updatePolicy(index, { endpoint_type: endpointType })}
                      />
                      <InputNumber
                        min={1}
                        precision={0}
                        disabled={disabled}
                        value={policy.priority}
                        onChange={(priority) => updatePolicy(index, { priority: Number(priority) || 1 })}
                        aria-label={`${bucket} priority`}
                      />
                      <Select
                        disabled={disabled}
                        style={{ width: 140 }}
                        options={PROVIDER_OPTIONS}
                        value={policy.provider}
                        onChange={(provider) => updatePolicy(index, { provider })}
                      />
                      <Space size={6}>
                        <Typography.Text>Enabled</Typography.Text>
                        <Switch
                          disabled={disabled}
                          checked={policy.enabled}
                          onChange={(enabled) => updatePolicy(index, { enabled })}
                        />
                      </Space>
                      <Space size={6}>
                        <Typography.Text>Fallback</Typography.Text>
                        <Switch
                          disabled={disabled}
                          checked={policy.fallback_enabled}
                          onChange={(fallbackEnabled) => updatePolicy(index, { fallback_enabled: fallbackEnabled })}
                        />
                      </Space>
                      {!policy.policy_id && (
                        <Button type="link" danger disabled={disabled} onClick={() => removeUnsavedPolicy(index)}>
                          Remove
                        </Button>
                      )}
                    </Space>
                  ))}
                </Space>
              )}
            </div>
          );
        })}
      </Space>
    </Card>
  );
}
