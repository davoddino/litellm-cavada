"use client";

import { Alert, Card, Col, Row, Space, Spin, Tabs, Tag, Typography } from "antd";
import { useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { listCavadaLabsResource } from "./api";
import CavadaLabsChatbotCreator from "./CavadaLabsChatbotCreator";
import CavadaLabsResourcePanel from "./CavadaLabsResourcePanel";
import CavadaLabsUsageActivityPanel from "./CavadaLabsUsageActivityPanel";
import CavadaLabsUsageDiagnosticsPanel from "./CavadaLabsUsageDiagnosticsPanel";
import { buildCavadaLabsResourceConfigs } from "./resourceConfigs";
import type { CavadaLabsResourceConfig, CavadaLabsRuntimeContext } from "./types";
import { statusColor } from "./utils";

const { Title, Text } = Typography;

interface CavadaLabsDashboardProps {
  accessToken: string | null;
  userRole?: string | null;
  initialResource?: string;
  initialTab?: string;
}

const emptyContext: CavadaLabsRuntimeContext = {
  companies: [],
  projects: [],
  chatbots: [],
  ragCollections: [],
  nodes: [],
};

const countFromResponse = (response: any, key: string): number => {
  if (typeof response?.count === "number") return response.count;
  if (Array.isArray(response?.[key])) return response[key].length;
  return 0;
};

const tabKeys = new Set(["overview", "tenants", "runtime", "knowledge", "safety", "billing", "compliance"]);

const resourceTabMap: Record<string, string> = {
  companies: "tenants",
  projects: "tenants",
  chatbots: "tenants",
  webTokens: "tenants",
  modelPolicies: "runtime",
  nodes: "runtime",
  modelLoadRequests: "runtime",
  gpuLocks: "runtime",
  ragCollections: "knowledge",
  ragDocuments: "knowledge",
  ragAssignments: "knowledge",
  guardrailPolicies: "safety",
  guardrailDecisions: "safety",
  billingReports: "billing",
  complianceDocuments: "compliance",
  complianceEvidence: "compliance",
  processingActivities: "compliance",
  dataSubjectRequests: "compliance",
  aiSystemAssessments: "compliance",
};

const resolveActiveTab = (
  searchParams: Pick<URLSearchParams, "get">,
  initialTab?: string,
  initialResource?: string,
): string => {
  const tab = searchParams.get("tab");
  if (tab && tabKeys.has(tab)) return tab;

  const resource = searchParams.get("resource");
  if (resource && resourceTabMap[resource]) return resourceTabMap[resource];

  if (initialResource && resourceTabMap[initialResource]) return resourceTabMap[initialResource];
  if (initialTab && tabKeys.has(initialTab)) return initialTab;

  return "overview";
};

const PanelStack = ({
  configs,
  accessToken,
  context,
  onMutated,
  initialDetailsByResource,
}: {
  configs: CavadaLabsResourceConfig[];
  accessToken: string | null;
  context: CavadaLabsRuntimeContext;
  onMutated: () => void;
  initialDetailsByResource?: Record<string, string | null | undefined>;
}) => (
  <Space direction="vertical" size={16} className="w-full">
    {configs.map((config) => (
      <CavadaLabsResourcePanel
        key={config.key}
        accessToken={accessToken}
        config={config}
        context={context}
        onMutated={onMutated}
        initialDetailsId={initialDetailsByResource?.[config.key] ?? null}
      />
    ))}
  </Space>
);

const CavadaLabsDashboard: React.FC<CavadaLabsDashboardProps> = ({ accessToken, initialResource, initialTab }) => {
  const searchParams = useSearchParams();
  const [context, setContext] = useState<CavadaLabsRuntimeContext>(emptyContext);
  const [referenceLoading, setReferenceLoading] = useState(false);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [overviewCounts, setOverviewCounts] = useState<Record<string, number>>({});
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const requestedTab = useMemo(
    () => resolveActiveTab(searchParams, initialTab, initialResource),
    [initialResource, initialTab, searchParams],
  );
  const [activeTabKey, setActiveTabKey] = useState(requestedTab);

  const refreshAll = useCallback(() => setRefreshNonce((value) => value + 1), []);

  useEffect(() => {
    setActiveTabKey(requestedTab);
  }, [requestedTab]);

  const loadReferenceData = useCallback(async () => {
    if (!accessToken) return;

    setReferenceLoading(true);
    setReferenceError(null);
    try {
      const [companies, projects, chatbots, ragCollections, nodes] = await Promise.all([
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/companies"),
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/projects"),
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/chatbots"),
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/rag-collections"),
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/nodes"),
      ]);

      setContext({
        companies: companies.companies ?? [],
        projects: projects.projects ?? [],
        chatbots: chatbots.chatbots ?? [],
        ragCollections: ragCollections.rag_collections ?? [],
        nodes: nodes.nodes ?? [],
      });
    } catch (err) {
      setReferenceError(err instanceof Error ? err.message : String(err));
      setContext(emptyContext);
    } finally {
      setReferenceLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadReferenceData();
  }, [loadReferenceData, refreshNonce]);

  const firstProjectId = context.projects[0]?.project_id;

  const loadOverview = useCallback(async () => {
    if (!accessToken) return;

    setOverviewLoading(true);
    const requests: Array<Promise<[string, number]>> = [
      Promise.resolve<[string, number]>(["companies", context.companies.length]),
      Promise.resolve<[string, number]>(["projects", context.projects.length]),
      Promise.resolve<[string, number]>(["chatbots", context.chatbots.length]),
      Promise.resolve<[string, number]>(["nodes", context.nodes.length]),
      listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/web-tokens").then(
        (data) => ["webTokens", countFromResponse(data, "web_tokens")] as [string, number],
      ),
      listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/model-load-requests").then(
        (data) => ["modelLoadRequests", countFromResponse(data, "model_load_requests")] as [string, number],
      ),
      listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/guardrail-policies").then(
        (data) => ["guardrailPolicies", countFromResponse(data, "guardrail_policies")] as [string, number],
      ),
      listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/billing-reports").then(
        (data) => ["billingReports", countFromResponse(data, "billing_reports")] as [string, number],
      ),
    ];

    if (firstProjectId) {
      requests.push(
        listCavadaLabsResource<Record<string, any>>(accessToken, "/cavadalabs/model-policies", {
          project_id: firstProjectId,
        }).then((data) => ["modelPolicies", countFromResponse(data, "model_policies")] as [string, number]),
      );
    }

    const settled = await Promise.allSettled(requests);
    const nextCounts: Record<string, number> = {};
    settled.forEach((result) => {
      if (result.status === "fulfilled") {
        const [key, value] = result.value;
        nextCounts[key] = value;
      }
    });
    setOverviewCounts(nextCounts);
    setOverviewLoading(false);
  }, [
    accessToken,
    context.chatbots.length,
    context.companies.length,
    context.nodes.length,
    context.projects.length,
    firstProjectId,
  ]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview, refreshNonce]);

  const configs = useMemo(() => buildCavadaLabsResourceConfigs(context), [context]);
  const initialDetailsByResource = useMemo(
    () => ({
      companies: searchParams.get("company_id"),
      projects: searchParams.get("project_id"),
    }),
    [searchParams],
  );

  const readiness: Array<{ label: string; status: "ready" | "pending"; detail: string }> = [
    {
      label: "Tenant model",
      status: context.companies.length > 0 && context.projects.length > 0 ? "ready" : "pending",
      detail: `${context.companies.length} companies, ${context.projects.length} projects`,
    },
    {
      label: "Chatbot runtime",
      status: context.chatbots.length > 0 && (overviewCounts.modelPolicies ?? 0) > 0 ? "ready" : "pending",
      detail: `${context.chatbots.length} chatbots, ${overviewCounts.modelPolicies ?? 0} model policies`,
    },
    {
      label: "Hosted nodes",
      status: context.nodes.length > 0 ? "ready" : "pending",
      detail: `${context.nodes.length} registered nodes`,
    },
    {
      label: "Governance",
      status: (overviewCounts.guardrailPolicies ?? 0) > 0 ? "ready" : "pending",
      detail: `${overviewCounts.guardrailPolicies ?? 0} guardrail policies`,
    },
  ];

  if (!accessToken) {
    return (
      <div className="m-8 p-2">
        <Alert type="warning" showIcon message="Missing access token" />
      </div>
    );
  }

  return (
    <div className="w-full mx-auto flex-auto overflow-y-auto m-8 p-2">
      <div className="mb-5 flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Title level={3} className="!mb-1">
            CavadaLabs
          </Title>
          <Text type="secondary">
            Dispatcher control plane, hosted runtime, RAG, billing, compliance, and guardrails.
          </Text>
        </div>
        {referenceLoading || overviewLoading ? <Spin /> : null}
      </div>

      {referenceError ? <Alert type="error" showIcon className="mb-4" message={referenceError} /> : null}

      <Tabs
        activeKey={activeTabKey}
        onChange={setActiveTabKey}
        items={[
          {
            key: "overview",
            label: "Overview",
            children: (
              <Space direction="vertical" size={16} className="w-full">
                <Row gutter={[12, 12]}>
                  {[
                    ["Companies", overviewCounts.companies ?? 0],
                    ["Projects", overviewCounts.projects ?? 0],
                    ["Chatbots", overviewCounts.chatbots ?? 0],
                    ["Web tokens", overviewCounts.webTokens ?? 0],
                    ["Nodes", overviewCounts.nodes ?? 0],
                    ["Load queue", overviewCounts.modelLoadRequests ?? 0],
                    ["Guardrails", overviewCounts.guardrailPolicies ?? 0],
                    ["Billing reports", overviewCounts.billingReports ?? 0],
                  ].map(([label, value]) => (
                    <Col xs={12} md={6} xl={3} key={label}>
                      <Card size="small">
                        <Text type="secondary">{label}</Text>
                        <div className="mt-1 text-2xl font-semibold">{value}</div>
                      </Card>
                    </Col>
                  ))}
                </Row>

                <section className="rounded-md border border-gray-200 bg-white p-4">
                  <Title level={4} className="!mb-3">
                    Readiness
                  </Title>
                  <Space direction="vertical" size={8} className="w-full">
                    {readiness.map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between border-b border-gray-100 pb-2 last:border-b-0 last:pb-0"
                      >
                        <div>
                          <Text strong>{item.label}</Text>
                          <div>
                            <Text type="secondary">{item.detail}</Text>
                          </div>
                        </div>
                        <Tag color={statusColor(item.status)}>{item.status}</Tag>
                      </div>
                    ))}
                  </Space>
                </section>
              </Space>
            ),
          },
          {
            key: "tenants",
            label: "Tenants",
            children: (
              <Space direction="vertical" size={16} className="w-full">
                <CavadaLabsChatbotCreator accessToken={accessToken} context={context} onCreated={refreshAll} />
                <PanelStack
                  configs={[configs.companies, configs.projects, configs.chatbots, configs.webTokens]}
                  accessToken={accessToken}
                  context={context}
                  onMutated={refreshAll}
                  initialDetailsByResource={initialDetailsByResource}
                />
              </Space>
            ),
          },
          {
            key: "runtime",
            label: "Runtime",
            children: (
              <PanelStack
                configs={[configs.modelPolicies, configs.nodes, configs.modelLoadRequests, configs.gpuLocks]}
                accessToken={accessToken}
                context={context}
                onMutated={refreshAll}
              />
            ),
          },
          {
            key: "knowledge",
            label: "Knowledge",
            children: (
              <PanelStack
                configs={[configs.ragCollections, configs.ragDocuments, configs.ragAssignments]}
                accessToken={accessToken}
                context={context}
                onMutated={refreshAll}
              />
            ),
          },
          {
            key: "safety",
            label: "Safety",
            children: (
              <PanelStack
                configs={[configs.guardrailPolicies, configs.guardrailDecisions]}
                accessToken={accessToken}
                context={context}
                onMutated={refreshAll}
              />
            ),
          },
          {
            key: "billing",
            label: "Billing",
            children: (
              <Space direction="vertical" size={16} className="w-full">
                <CavadaLabsUsageActivityPanel accessToken={accessToken} context={context} />
                <CavadaLabsUsageDiagnosticsPanel accessToken={accessToken} context={context} />
                <PanelStack
                  configs={[configs.billingReports]}
                  accessToken={accessToken}
                  context={context}
                  onMutated={refreshAll}
                />
              </Space>
            ),
          },
          {
            key: "compliance",
            label: "Compliance",
            children: (
              <PanelStack
                configs={[
                  configs.complianceDocuments,
                  configs.complianceEvidence,
                  configs.processingActivities,
                  configs.dataSubjectRequests,
                  configs.aiSystemAssessments,
                ]}
                accessToken={accessToken}
                context={context}
                onMutated={refreshAll}
              />
            ),
          },
        ]}
      />
    </div>
  );
};

export default CavadaLabsDashboard;
