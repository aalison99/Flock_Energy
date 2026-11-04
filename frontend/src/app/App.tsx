import { useState } from "react";
import { BrowserRouter } from "react-router";
import { makeQueryClient, Providers } from "./providers";
import { AppRoutes } from "./router";

export function App() {
  const [queryClient] = useState(makeQueryClient);
  return (
    <Providers client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Providers>
  );
}
