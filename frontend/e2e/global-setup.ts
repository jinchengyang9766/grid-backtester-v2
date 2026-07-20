import { startServers, type RunningServers } from "./fixtures/servers";

let servers: RunningServers | null = null;

export default async function globalSetup() {
  servers = await startServers();
  // Playwright calls the returned function as the global teardown, so the
  // servers and temporary database are cleaned up even when tests fail.
  return async () => {
    await servers?.shutdown();
    servers = null;
  };
}
