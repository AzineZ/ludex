import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ServerStatus from "../../components/ServerStatus";

describe("ServerStatus", () => {
   it.each([
      ["connected", "Server: connected"],
      ["checking", "Server: pending"],
      ["unavailable", "Server: unavailable"],
   ] as const)("renders the %s state with a stable state class", (state, label) => {
      render(<ServerStatus connectionState={state} />);

      const status = screen.getByRole("status");
      expect(status).toHaveTextContent(label);
      expect(status).toHaveClass(`app__status--${state}`);
      expect(status).toHaveAttribute("aria-live", "polite");
   });
});
