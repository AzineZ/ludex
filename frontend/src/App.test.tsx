import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { getHealth, type HealthResponse } from "./api";

vi.mock("./api", () => ({
   getHealth: vi.fn(),
}));

const mockedGetHealth = vi.mocked(getHealth);

describe("App", () => {
   beforeEach(() => {
      mockedGetHealth.mockReset();
   });

   it("renders while checking the backend connection", () => {
      mockedGetHealth.mockImplementation(
         () => new Promise<HealthResponse>(() => {})
      );

      render(<App />);

      expect(
         screen.getByRole("heading", { name: "Find your next game." })
      ).toBeInTheDocument();
      expect(screen.getByText("Backend: checking")).toBeInTheDocument();
   });

   it("shows connected when the health request succeeds", async () => {
      mockedGetHealth.mockResolvedValue({
         status: "healthy",
         database: "connected",
      });

      render(<App />);

      expect(await screen.findByText("Backend: connected")).toBeInTheDocument();
   });

   it("shows unavailable when the health request fails", async () => {
      mockedGetHealth.mockRejectedValue(new Error("Backend unavailable"));

      render(<App />);

      expect(
         await screen.findByText("Backend: unavailable")
      ).toBeInTheDocument();
   });
});
