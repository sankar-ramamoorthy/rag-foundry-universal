import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createHttpProductApi } from "./api/productApi";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");

// Same-origin: the dev proxy (vite.config.ts) and the production gateway both
// serve /v1/product, so the browser never needs a service address.
createRoot(root).render(
  <StrictMode>
    <App api={createHttpProductApi()} />
  </StrictMode>,
);
