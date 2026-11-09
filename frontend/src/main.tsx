import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { PortalGate } from "./PortalGate";
import { installPortalFetch } from "./portalAuth";
import "./index.css";

installPortalFetch();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <PortalGate>
        <App />
      </PortalGate>
    </BrowserRouter>
  </StrictMode>,
);
