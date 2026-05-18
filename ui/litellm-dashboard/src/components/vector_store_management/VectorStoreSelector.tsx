import React, { useEffect, useState } from "react";
import { Select } from "antd";
import { VectorStore } from "./types";
import { vectorStoreListCall } from "../networking";
interface VectorStoreSelectorProps {
  onChange: (selectedVectorStores: string[]) => void;
  value?: string[];
  className?: string;
  accessToken: string;
  placeholder?: string;
  disabled?: boolean;
  companyId?: string | null;
  projectId?: string | null;
}

const VectorStoreSelector: React.FC<VectorStoreSelectorProps> = ({
  onChange,
  value,
  className,
  accessToken,
  placeholder = "Select vector stores",
  disabled = false,
  companyId,
  projectId,
}) => {
  const [vectorStores, setVectorStores] = useState<VectorStore[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasLoadedVectorStores, setHasLoadedVectorStores] = useState(false);

  useEffect(() => {
    const fetchVectorStores = async () => {
      if (!accessToken) return;

      setLoading(true);
      setHasLoadedVectorStores(false);
      try {
        const filters =
          companyId || projectId ? { company_id: companyId || undefined, project_id: projectId || undefined } : undefined;
        const response = filters
          ? await vectorStoreListCall(accessToken, 1, 100, filters)
          : await vectorStoreListCall(accessToken);
        setVectorStores(response.data || []);
        setHasLoadedVectorStores(true);
      } catch (error) {
        console.error("Error fetching vector stores:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchVectorStores();
  }, [accessToken, companyId, projectId]);

  useEffect(() => {
    if (!value || value.length === 0 || loading || !hasLoadedVectorStores) {
      return;
    }
    const availableVectorStoreIds = new Set(vectorStores.map((store) => store.vector_store_id));
    const nextValue = value.filter((vectorStoreId) => availableVectorStoreIds.has(vectorStoreId));
    if (nextValue.length !== value.length) {
      onChange(nextValue);
    }
  }, [hasLoadedVectorStores, loading, onChange, value, vectorStores]);

  const options = vectorStores.map((store) => {
    const displayName = store.vector_store_name || store.vector_store_id;
    const contextParts = [store.company_name || store.company_id, store.project_name || store.project_id].filter(Boolean);
    const contextLabel = contextParts.length > 0 ? ` - ${contextParts.join(" / ")}` : "";
    return {
      label: `${displayName} (${store.vector_store_id})${contextLabel}`,
      value: store.vector_store_id,
      title: store.vector_store_description || store.vector_store_id,
    };
  });

  return (
    <div>
      <Select
        mode="multiple"
        placeholder={placeholder}
        onChange={onChange}
        value={value}
        loading={loading}
        className={className}
        allowClear
        options={options}
        optionFilterProp="label"
        showSearch
        style={{ width: "100%" }}
        disabled={disabled}
      />
    </div>
  );
};

export default VectorStoreSelector;
