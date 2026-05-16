import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "../../../tests/test-utils";
import CavadaLabsChatbotCreatorResult from "./CavadaLabsChatbotCreatorResult";

describe("CavadaLabsChatbotCreatorResult", () => {
  it("should show one-time server and browser token secrets only once", () => {
    renderWithProviders(
      <CavadaLabsChatbotCreatorResult
        onClose={vi.fn()}
        result={{
          chatbot: {
            chatbot_id: "chatbot-1",
            company_id: "company-1",
            project_id: "project-1",
            name: "Support Bot",
          },
          serverKeyResponse: {
            key: "sk-live-once",
            token: "hashed-server-key",
            cavadalabs_chatbot_id: "chatbot-1",
          },
          webTokenResponse: {
            token: "clwt-live-once",
            token_id: "web-token-1",
            cavadalabs_chatbot_id: "chatbot-1",
          },
        }}
      />,
    );

    expect(screen.getByText("Server API key")).toBeInTheDocument();
    expect(screen.getByText("Browser web token")).toBeInTheDocument();
    expect(screen.getAllByText("sk-live-once")).toHaveLength(1);
    expect(screen.getAllByText("clwt-live-once")).toHaveLength(1);
    expect(screen.getByText((content) => content.includes('"key": "[shown once above]"'))).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('"token": "[shown once above]"'))).toBeInTheDocument();
  });
});
