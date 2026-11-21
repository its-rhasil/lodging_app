import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { OnlineProvider } from "./online";
import { ServerGate } from "./ServerGate";
import { SessionProvider } from "./session";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OnlineProvider>
      <ServerGate>
        <SessionProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </SessionProvider>
      </ServerGate>
    </OnlineProvider>
  </StrictMode>,
);
