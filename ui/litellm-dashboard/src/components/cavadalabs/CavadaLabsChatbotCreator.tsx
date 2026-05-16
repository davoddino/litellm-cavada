"use client";

import { Alert, Button, Form, Modal, Typography } from "antd";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createCavadaLabsResource, listCavadaLabsResource, postCavadaLabsAction } from "./api";
import {
  buildChatbotCreatePayload,
  buildChatbotServerKeyCreatePayload,
  buildChatbotServerKeyUpdatePayload,
  buildChatbotWebTokenPayload,
  extractCreatedChatbotId,
  initialChatbotCreatorValues,
  modelPolicyOptions,
  projectsForCompany,
  serverKeyOptions,
  type CavadaLabsChatbotCreatorValues,
} from "./chatbotCreatorPayload";
import CavadaLabsChatbotCreatorForm from "./CavadaLabsChatbotCreatorForm";
import CavadaLabsChatbotCreatorResult, {
  type CavadaLabsChatbotCreatorResultValue,
} from "./CavadaLabsChatbotCreatorResult";
import type { CavadaLabsRecord, CavadaLabsRuntimeContext } from "./types";
import { toOptions } from "./utils";

const { Text, Title } = Typography;

interface CavadaLabsChatbotCreatorProps {
  accessToken: string | null;
  context: CavadaLabsRuntimeContext;
  onCreated?: () => void;
}

const CavadaLabsChatbotCreator: React.FC<CavadaLabsChatbotCreatorProps> = ({ accessToken, context, onCreated }) => {
  const [form] = Form.useForm<CavadaLabsChatbotCreatorValues>();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [policies, setPolicies] = useState<CavadaLabsRecord[]>([]);
  const [keys, setKeys] = useState<CavadaLabsRecord[]>([]);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [keyLoading, setKeyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CavadaLabsChatbotCreatorResultValue | null>(null);

  const selectedCompanyId = Form.useWatch("company_id", form);
  const selectedProjectId = Form.useWatch("project_id", form);
  const selectedStatus = Form.useWatch("status", form);
  const serverKeyMode = Form.useWatch("server_key_mode", form);
  const issueWebToken = Form.useWatch("issue_web_token", form);

  const companyOptions = useMemo(() => toOptions(context.companies, "company_id", "legal_name"), [context.companies]);
  const projectOptions = useMemo(
    () => toOptions(projectsForCompany(context, selectedCompanyId), "project_id", "name"),
    [context, selectedCompanyId],
  );
  const ragOptions = useMemo(
    () => toOptions(context.ragCollections, "collection_id", "name"),
    [context.ragCollections],
  );
  const policyOptions = useMemo(() => modelPolicyOptions(policies), [policies]);
  const keyOptions = useMemo(() => serverKeyOptions(keys), [keys]);
  const canCreate = companyOptions.length > 0 && context.projects.length > 0;

  const openCreator = () => {
    setError(null);
    setResult(null);
    form.setFieldsValue(initialChatbotCreatorValues(context));
    setOpen(true);
  };

  const handleCompanyChange = (companyId: string) => {
    const nextProjectId = projectsForCompany(context, companyId)[0]?.project_id;
    form.setFieldsValue({
      project_id: nextProjectId ? String(nextProjectId) : undefined,
      model_policy_id: undefined,
      existing_server_key: undefined,
    });
  };

  useEffect(() => {
    if (!open || !accessToken || !selectedProjectId) {
      setPolicies([]);
      return;
    }

    let ignore = false;
    setPolicyLoading(true);
    listCavadaLabsResource<CavadaLabsRecord>(accessToken, "/cavadalabs/model-policies", {
      project_id: selectedProjectId,
    })
      .then((response) => {
        if (ignore) return;
        setPolicies(Array.isArray(response.model_policies) ? response.model_policies : []);
      })
      .catch((err) => {
        if (ignore) return;
        setPolicies([]);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!ignore) setPolicyLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [accessToken, open, selectedProjectId]);

  useEffect(() => {
    if (!open || !accessToken || !selectedCompanyId || !selectedProjectId) {
      setKeys([]);
      return;
    }

    let ignore = false;
    setKeyLoading(true);
    listCavadaLabsResource<CavadaLabsRecord>(accessToken, "/key/list", {
      return_full_object: true,
      include_team_keys: true,
      include_created_by_keys: true,
      cavadalabs_company_id: selectedCompanyId,
      cavadalabs_project_id: selectedProjectId,
      page: 1,
      size: 100,
    })
      .then((response) => {
        if (ignore) return;
        setKeys(Array.isArray(response.keys) ? response.keys : []);
      })
      .catch((err) => {
        if (ignore) return;
        setKeys([]);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!ignore) setKeyLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [accessToken, open, selectedCompanyId, selectedProjectId]);

  const submit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      if (values.issue_web_token && values.status !== "published") {
        setError("Publish the chatbot before issuing a browser web token.");
        return;
      }

      setSubmitting(true);
      setError(null);
      const chatbot = await createCavadaLabsResource<CavadaLabsRecord>(
        accessToken,
        "/cavadalabs/chatbots",
        buildChatbotCreatePayload(values),
      );
      const chatbotId = extractCreatedChatbotId(chatbot);
      const selectedPolicy = policies.find((policy) => policy.policy_id === values.model_policy_id);
      const selectedKey = keys.find((key) => String(key.token ?? key.key) === values.existing_server_key);
      const serverKeyCreatePayload = buildChatbotServerKeyCreatePayload(values, chatbotId, selectedPolicy);
      const serverKeyUpdatePayload = buildChatbotServerKeyUpdatePayload(values, chatbotId, selectedKey);
      const serverKeyResponse = serverKeyCreatePayload
        ? await createCavadaLabsResource<CavadaLabsRecord>(accessToken, "/key/generate", serverKeyCreatePayload)
        : serverKeyUpdatePayload
          ? await postCavadaLabsAction<CavadaLabsRecord>(accessToken, "/key/update", serverKeyUpdatePayload)
          : undefined;
      const tokenPayload = buildChatbotWebTokenPayload(values, chatbotId);
      const webTokenResponse = tokenPayload
        ? await createCavadaLabsResource<CavadaLabsRecord>(accessToken, "/cavadalabs/web-tokens", tokenPayload)
        : undefined;

      setOpen(false);
      form.resetFields();
      setResult({ chatbot, serverKeyResponse, webTokenResponse });
      onCreated?.();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, form, onCreated]);

  return (
    <section className="rounded-md border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Title level={4} className="!mb-1">
            Chatbot Creator
          </Title>
          <Text type="secondary">Create a Project-scoped chatbot and optional browser token.</Text>
        </div>
        <Button type="primary" onClick={openCreator} disabled={!canCreate}>
          Create chatbot
        </Button>
      </div>

      {!canCreate ? (
        <Alert
          type="info"
          showIcon
          className="mt-4"
          message="Create a Company and Project before creating a chatbot."
        />
      ) : null}

      <Modal
        open={open}
        title="Create chatbot"
        onCancel={() => setOpen(false)}
        onOk={submit}
        confirmLoading={submitting}
        width={920}
        destroyOnHidden
      >
        {error ? <Alert type="error" showIcon className="mb-4" message={error} /> : null}
        <CavadaLabsChatbotCreatorForm
          form={form}
          companyOptions={companyOptions}
          projectOptions={projectOptions}
          policyOptions={policyOptions}
          serverKeyOptions={keyOptions}
          ragOptions={ragOptions}
          policyLoading={policyLoading}
          keyLoading={keyLoading}
          selectedStatus={selectedStatus}
          serverKeyMode={serverKeyMode}
          issueWebToken={issueWebToken}
          onCompanyChange={handleCompanyChange}
        />
      </Modal>

      <CavadaLabsChatbotCreatorResult result={result} onClose={() => setResult(null)} />
    </section>
  );
};

export default CavadaLabsChatbotCreator;
