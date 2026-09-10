import { afterEach, describe, expect, it, vi } from "vitest";
import type { MeasureApiClient } from "../api-client";
import { AuthController, type AuthState } from "./auth";

type AuthApi = Pick<
  MeasureApiClient,
  | "startContributionDeviceAuth"
  | "getContributionDeviceAuth"
  | "saveContributionToken"
  | "disconnectContributionAuth"
>;

function state(): AuthState {
  return {
    contributionAuthBusy: false,
    contributionAuthError: "",
  };
}

function api(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    startContributionDeviceAuth: async () => ({
      flow_id: "flow-1",
      user_code: "ABCD-EFGH",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    }),
    getContributionDeviceAuth: async () => ({ status: "pending" }),
    saveContributionToken: async () => ({
      connected: true,
      method: "token",
      identity: { login: "octocat" },
    }),
    disconnectContributionAuth: async () => ({ connected: false }),
    ...overrides,
  };
}

afterEach(() => vi.useRealTimers());

describe("contribution authentication", () => {
  it("polls a device flow until GitHub authorizes it", async () => {
    vi.useFakeTimers();
    const authState = state();
    const changed = vi.fn();
    const controller = new AuthController(authState, () => api({
      getContributionDeviceAuth: async () => ({
        status: "authorized",
        auth: { connected: true, method: "device", identity: { login: "octocat" } },
      }),
    }), changed);

    await controller.startDeviceFlow();
    expect(authState.contributionDeviceStatus?.status).toBe("pending");

    await vi.advanceTimersByTimeAsync(5_000);

    expect(authState.contributionAuth?.identity?.login).toBe("octocat");
    expect(authState.contributionDeviceFlow).toBeUndefined();
    expect(changed).toHaveBeenCalled();
  });

  it("honors slow-down responses and expires the flow", async () => {
    vi.useFakeTimers();
    const authState = state();
    let polls = 0;
    const controller = new AuthController(authState, () => api({
      startContributionDeviceAuth: async () => ({
        flow_id: "flow-1",
        user_code: "ABCD-EFGH",
        verification_uri: "https://github.com/login/device",
        expires_in: 16,
        interval: 5,
      }),
      getContributionDeviceAuth: async () => {
        polls += 1;
        return polls === 1 ? { status: "slow_down" } : { status: "pending" };
      },
    }), () => undefined);

    await controller.startDeviceFlow();
    await vi.advanceTimersByTimeAsync(5_000);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(polls).toBe(2);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(authState.contributionDeviceStatus?.status).toBe("expired");
  });

  it("stops an active poll when disposed", async () => {
    vi.useFakeTimers();
    const authState = state();
    const poll = vi.fn(async () => ({ status: "pending" as const }));
    const controller = new AuthController(authState, () => api({ getContributionDeviceAuth: poll }), () => undefined);

    await controller.startDeviceFlow();
    controller.dispose();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(poll).not.toHaveBeenCalled();
    expect(authState.contributionAuthBusy).toBe(false);
  });

  it("owns token fallback, disconnect, and their errors", async () => {
    const authState = state();
    let fail = false;
    const controller = new AuthController(authState, () => api({
      disconnectContributionAuth: async () => {
        if (fail) throw new Error("GitHub is unavailable");
        return { connected: false };
      },
    }), () => undefined);

    await controller.saveToken("token");
    expect(authState.contributionAuth?.method).toBe("token");

    await controller.disconnect();
    expect(authState.contributionAuth?.connected).toBe(false);

    fail = true;
    await controller.disconnect();
    expect(authState.contributionAuthError).toBe("GitHub is unavailable");
    expect(authState.contributionAuthBusy).toBe(false);
  });
});
