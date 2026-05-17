import type { CavadaLabsSelectOption } from "./types";

const readModelName = (item: unknown): string | null => {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return null;

  const record = item as Record<string, unknown>;
  const value = record.id ?? record.model_name ?? record.model_group ?? record.model;
  return typeof value === "string" ? value : null;
};

export const extractModelNamesFromValue = (value: unknown): string[] => {
  const rawItems = Array.isArray(value) ? value : value ? [value] : [];
  const names = rawItems
    .map(readModelName)
    .filter((model): model is string => Boolean(model?.trim()))
    .map((model) => model.trim());

  return Array.from(new Set(names));
};

export const extractModelNamesFromResponse = (response: unknown): string[] => {
  if (Array.isArray(response)) return extractModelNamesFromValue(response);
  if (!response || typeof response !== "object") return [];

  const record = response as Record<string, unknown>;
  return extractModelNamesFromValue(record.data ?? record.models ?? record.model_list);
};

export const modelNamesToOptions = (models: string[]): CavadaLabsSelectOption[] =>
  extractModelNamesFromValue(models).map((model) => ({
    label: model,
    value: model,
  }));
