import React from "react";
import ReactDOM from "react-dom/client";

import { AppProviders } from "./app/providers";
import { getEnvironment } from "./lib/env";
import "./styles/tokens.css";
import "./styles/globals.css";

getEnvironment();

const root = document.getElementById("root");

if (root === null) {
  throw new Error("WorkflowForge root element was not found.");
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <AppProviders />
  </React.StrictMode>,
);
