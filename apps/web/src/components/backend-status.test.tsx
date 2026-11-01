import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendStatus } from "./backend-status";
import Home from "@/app/page";

afterEach(() => vi.unstubAllGlobals());

describe("backend connection", () => {
  it("announces loading and then a verified success", async () => {
    let complete!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { complete = resolve; });
    const fetcher = vi.fn(() => pending);
    vi.stubGlobal("fetch", fetcher);
    render(<BackendStatus />);
    expect(screen.getByRole("status")).toHaveTextContent("Checking backend");
    expect(screen.getByRole("button")).toBeDisabled();
    await act(async () => complete(new Response(JSON.stringify({ status: "ready" }))));
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
    expect(fetcher.mock.calls[0]).toBeDefined();
  });

  it.each(["network", "unavailable", "malformed"])("shows safe error for %s and supports retry", async (failure) => {
    const fetcher = vi.fn();
    if (failure === "network") fetcher.mockRejectedValueOnce(new Error("private internal value"));
    else fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ status: "wrong" }), { status: failure === "unavailable" ? 503 : 200 }));
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ status: "ready" })));
    vi.stubGlobal("fetch", fetcher);
    render(<BackendStatus />);
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
    expect(screen.queryByText("private internal value")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check connection" }));
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][0]).toBe("http://127.0.0.1:8001/api/v1/health/ready");
  });

  it("renders research scope without fabricated clinical metrics", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("careful research");
    expect(screen.getByText("Research prototype")).toBeInTheDocument();
    expect(screen.getByText(/not a clinically validated medical device/)).toBeInTheDocument();
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  });
});
