import { ApiError } from "./api-client";
import { MeasureAppController } from "./app-controller";
import { api, connection, state } from "./testing/controller";

describe("measure app controller: contribution", () => {
  it("runs device login, token fallback, disconnect, preview, and submit contribution actions", async () => {
    vi.useFakeTimers();
    const appState = state();
    let devicePolls = 0;
    const controller = new MeasureAppController(appState, () => api({
      getContributionDeviceAuth: async () => {
        devicePolls += 1;
        return { status: "authorized", auth: { connected: true, identity: { login: "octocat" }, method: "device" } };
      },
      previewContribution: async (_sessionId, request) => ({
        eligible: true,
        repository: "bramstroker/homeassistant-powercalc",
        base_branch: "master",
        manufacturer_name: request.manufacturer_name,
        manufacturer_directory: "signify",
        model_id: request.model_id,
        product_name: request.product_name,
        contributor: request.contributor,
        device_info: {},
        home_assistant: {},
        notes: request.notes,
        files: [{ path: "profile_library/signify/LCT010/model.json", content: "{}" }],
        model_json: {},
        commit_message: "Add Signify LCT010",
        pr_title: "Add Signify LCT010",
        pr_body: "",
        branch_name: "measure/signify-lct010",
        warnings: [],
      }),
    }), () => connection(), () => undefined);
    appState.snapshot = { state: "completed", session_id: "session-1" };

    await controller.startContributionDeviceAuth();
    expect(appState.contributionDeviceFlow?.flow_id).toBe("flow-1");
    expect(appState.contributionDeviceStatus?.status).toBe("pending");
    expect(devicePolls).toBe(0);

    await vi.advanceTimersByTimeAsync(4_999);
    expect(devicePolls).toBe(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(appState.contributionAuth?.identity?.login).toBe("octocat");
    expect(appState.contributionDeviceFlow).toBeUndefined();

    await controller.saveContributionToken("token");
    expect(appState.contributionAuth?.method).toBe("token");

    await controller.previewContribution({ manufacturer_name: "Signify", model_id: "LCT010", product_name: "Hue lamp", contributor: "octocat", notes: "No aliases." });
    expect(appState.contributionPreview?.notes).toBe("No aliases.");

    controller.openProfile();
    expect(appState.view).toBe("profile");
    controller.openShare();
    expect(appState.view).toBe("share");
    controller.backToProfile();
    expect(appState.view).toBe("profile");
    controller.backToResult();
    expect(appState.view).toBe("result");

    await controller.submitContribution({ manufacturer_name: "Signify", model_id: "LCT010", product_name: "Hue lamp", contributor: "octocat", notes: "No aliases.", confirmed: true });
    expect(appState.contributionResult?.pull_request_url).toBe("https://github.com/pull/1");

    await controller.disconnectContributionAuth();
    expect(appState.contributionAuth?.connected).toBe(false);
    controller.dispose();
    vi.useRealTimers();
  });

  it("preserves contribution field errors for inline feedback", async () => {
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      previewContribution: async () => {
        throw new ApiError(
          "Product name must not start with the manufacturer",
          422,
          "invalid_metadata",
          "product_name",
        );
      },
    }), () => connection(), () => undefined);
    appState.snapshot = { state: "completed", session_id: "session-1" };

    await controller.previewContribution({
      manufacturer_name: "Signify",
      model_id: "LCT010",
      product_name: "Signify Hue lamp",
      contributor: "octocat",
      notes: "",
    });

    expect(appState.contributionError).toBe("Product name must not start with the manufacturer");
    expect(appState.contributionErrorField).toBe("product_name");
  });

  it("backs off automatic device polling and stops when the code expires", async () => {
    vi.useFakeTimers();
    const appState = state();
    let devicePolls = 0;
    const controller = new MeasureAppController(appState, () => api({
      startContributionDeviceAuth: async () => ({
        flow_id: "flow-1",
        user_code: "ABCD-EFGH",
        verification_uri: "https://github.com/login/device",
        expires_in: 16,
        interval: 5,
      }),
      getContributionDeviceAuth: async () => {
        devicePolls += 1;
        if (devicePolls === 1) return { status: "slow_down" };
        return { status: "pending" };
      },
    }), () => connection(), () => undefined);

    await controller.startContributionDeviceAuth();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(devicePolls).toBe(1);

    await vi.advanceTimersByTimeAsync(9_999);
    expect(devicePolls).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(devicePolls).toBe(2);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(appState.contributionDeviceStatus?.status).toBe("expired");
    await vi.advanceTimersByTimeAsync(30_000);
    expect(devicePolls).toBe(2);

    controller.dispose();
    vi.useRealTimers();
  });

  it("uses GitHub's retry interval and cancels polling on disposal", async () => {
    vi.useFakeTimers();
    const appState = state();
    let devicePolls = 0;
    const controller = new MeasureAppController(appState, () => api({
      getContributionDeviceAuth: async () => {
        devicePolls += 1;
        return { status: "slow_down", retry_after: 12 };
      },
    }), () => connection(), () => undefined);

    await controller.startContributionDeviceAuth();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(devicePolls).toBe(1);
    await vi.advanceTimersByTimeAsync(11_999);
    expect(devicePolls).toBe(1);

    controller.dispose();
    await vi.advanceTimersByTimeAsync(1);
    expect(devicePolls).toBe(1);
    vi.useRealTimers();
  });


});
