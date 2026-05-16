import { Alert, Modal, Typography } from "antd";
import React from "react";
import type { CavadaLabsRecord } from "./types";

const { Paragraph } = Typography;

export interface CavadaLabsChatbotCreatorResultValue {
  chatbot: CavadaLabsRecord;
  serverKeyResponse?: CavadaLabsRecord;
  webTokenResponse?: CavadaLabsRecord;
}

const redactOneTimeSecret = (
  record: CavadaLabsRecord | undefined,
  secretField: string,
): CavadaLabsRecord | undefined => {
  if (!record || record[secretField] === undefined) {
    return record;
  }

  return {
    ...record,
    [secretField]: "[shown once above]",
  };
};

const buildResultSummary = (result: CavadaLabsChatbotCreatorResultValue | null): CavadaLabsRecord => {
  if (!result) {
    return {};
  }

  return {
    chatbot: result.chatbot,
    serverKeyResponse: redactOneTimeSecret(result.serverKeyResponse, "key"),
    webTokenResponse: redactOneTimeSecret(result.webTokenResponse, "token"),
  };
};

const CavadaLabsChatbotCreatorResult: React.FC<{
  result: CavadaLabsChatbotCreatorResultValue | null;
  onClose: () => void;
}> = ({ result, onClose }) => {
  const resultSummary = buildResultSummary(result);

  return (
    <Modal open={Boolean(result)} title="Chatbot created" footer={null} onCancel={onClose} width={760}>
      {result?.serverKeyResponse?.key ? (
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message="Server API key"
          description={<Paragraph copyable>{String(result.serverKeyResponse.key)}</Paragraph>}
        />
      ) : null}
      {result?.webTokenResponse?.token ? (
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message="Browser web token"
          description={<Paragraph copyable>{String(result.webTokenResponse.token)}</Paragraph>}
        />
      ) : null}
      <pre className="max-h-80 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 text-xs">
        {JSON.stringify(resultSummary, null, 2)}
      </pre>
    </Modal>
  );
};

export default CavadaLabsChatbotCreatorResult;
