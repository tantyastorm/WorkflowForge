import { RouterProvider } from "react-router";

import { createAppRouter } from "./router";

export function App() {
  return <RouterProvider router={createAppRouter()} />;
}
