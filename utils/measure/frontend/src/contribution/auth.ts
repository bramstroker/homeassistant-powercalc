import { ApiError } from "../api-client";
import type { MeasureApiClient } from "../api-client";
import type {
  ContributionAuthDeviceStatus,
  ContributionAuthState,
  ContributionDeviceFlow,
} from "../types";

export interface AuthState {
  contributionAuth?: ContributionAuthState;
  contributionDeviceFlow?: ContributionDeviceFlow;
  contributionDeviceStatus?: ContributionAuthDeviceStatus;
  contributionAuthBusy: boolean;
  contributionAuthError: string;
}

type AuthApi = Pick<
  MeasureApiClient,
  | "startContributionDeviceAuth"
  | "getContributionDeviceAuth"
  | "saveContributionToken"
  | "disconnectContributionAuth"
>;

/** Owns the GitHub device-flow lifecycle, including polling, expiry, and stale responses. */
export class AuthController {
  private flowVersion = 0;
  private pollInterval = 0;
  private expiresAt = 0;
  private pollTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private readonly state: AuthState,
    private readonly api: () => AuthApi,
    private readonly changed: () => void,
  ) {}

  dispose(): void {
    this.stopPolling();
    this.state.contributionAuthBusy = false;
  }

  async startDeviceFlow(): Promise<void> {
    this.stopPolling();
    const version = this.flowVersion;
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.state.contributionDeviceFlow = undefined;
    this.state.contributionDeviceStatus = undefined;
    this.changed();
    try {
      const flow = await this.api().startContributionDeviceAuth();
      if (version !== this.flowVersion) return;
      this.state.contributionDeviceFlow = flow;
      this.state.contributionDeviceStatus = {
        status: "pending",
        message: "Waiting for GitHub authorization…",
      };
      this.pollInterval = Math.max(1, flow.interval);
      this.expiresAt = Date.now() + Math.max(0, flow.expires_in) * 1_000;
      this.schedulePoll(version);
    } catch (error) {
      if (version !== this.flowVersion) return;
      this.state.contributionAuthError = message(error);
    } finally {
      if (version === this.flowVersion) {
        this.state.contributionAuthBusy = false;
        this.changed();
      }
    }
  }

  async saveToken(token: string): Promise<void> {
    await this.run(async () => {
      this.state.contributionAuth = await this.api().saveContributionToken(token);
      this.clearFlow();
    });
  }

  async disconnect(): Promise<void> {
    await this.run(async () => {
      this.state.contributionAuth = await this.api().disconnectContributionAuth();
      this.clearFlow();
    });
  }

  private async poll(version: number): Promise<void> {
    const flowId = this.state.contributionDeviceFlow?.flow_id;
    if (!flowId || version !== this.flowVersion) return;
    if (Date.now() >= this.expiresAt) {
      this.expireFlow();
      return;
    }
    try {
      const status = await this.api().getContributionDeviceAuth(flowId);
      if (this.isStalePoll(version, flowId)) return;
      this.applyStatus(status, version);
    } catch (error) {
      if (this.isStalePoll(version, flowId)) return;
      this.handlePollError(error, version);
    } finally {
      if (version === this.flowVersion) this.changed();
    }
  }

  private isStalePoll(version: number, flowId: string): boolean {
    return version !== this.flowVersion || flowId !== this.state.contributionDeviceFlow?.flow_id;
  }

  private applyStatus(status: ContributionAuthDeviceStatus, version: number): void {
    this.state.contributionDeviceStatus = status;
    if (status.auth) this.state.contributionAuth = status.auth;
    this.state.contributionAuthError = "";

    if (status.status === "authorized") {
      this.state.contributionDeviceFlow = undefined;
      this.stopPolling();
      this.changed();
      return;
    }
    if (status.status !== "pending" && status.status !== "slow_down") return;

    if (status.status === "slow_down") {
      this.pollInterval = validRetryAfter(status.retry_after)
        ? Math.max(this.pollInterval, status.retry_after)
        : this.pollInterval + 5;
    }
    this.schedulePoll(version);
  }

  private handlePollError(error: unknown, version: number): void {
    if (error instanceof ApiError && error.status === 404) {
      this.expireFlow();
      return;
    }
    this.state.contributionAuthError = message(error);
    this.schedulePoll(version);
  }

  private schedulePoll(version: number): void {
    this.clearPollTimer();
    if (version !== this.flowVersion || !this.state.contributionDeviceFlow) return;
    const remaining = this.expiresAt - Date.now();
    if (remaining <= 0) {
      this.expireFlow();
      return;
    }
    const delay = Math.min(this.pollInterval * 1_000, remaining);
    this.pollTimer = setTimeout(() => {
      this.pollTimer = undefined;
      void this.poll(version);
    }, delay);
  }

  private expireFlow(): void {
    this.clearPollTimer();
    this.state.contributionDeviceStatus = {
      status: "expired",
      message: "This GitHub code expired. Request a new code to continue.",
    };
    this.changed();
  }

  private clearFlow(): void {
    this.stopPolling();
    this.state.contributionDeviceFlow = undefined;
    this.state.contributionDeviceStatus = undefined;
  }

  private stopPolling(): void {
    this.flowVersion += 1;
    this.clearPollTimer();
  }

  private clearPollTimer(): void {
    if (this.pollTimer === undefined) return;
    clearTimeout(this.pollTimer);
    this.pollTimer = undefined;
  }

  private async run(work: () => Promise<void>): Promise<void> {
    this.state.contributionAuthBusy = true;
    this.state.contributionAuthError = "";
    this.changed();
    try {
      await work();
    } catch (error) {
      this.state.contributionAuthError = message(error);
    } finally {
      this.state.contributionAuthBusy = false;
      this.changed();
    }
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function validRetryAfter(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
