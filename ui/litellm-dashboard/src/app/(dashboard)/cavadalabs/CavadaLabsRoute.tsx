"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import CavadaLabsDashboard from "@/components/cavadalabs/CavadaLabsDashboard";
import { Suspense } from "react";

interface CavadaLabsRouteProps {
  initialResource?: "companies" | "projects";
  initialTab?: "overview" | "tenants" | "runtime" | "knowledge" | "safety" | "billing" | "compliance";
}

const CavadaLabsRoute = ({ initialResource, initialTab }: CavadaLabsRouteProps) => {
  const { accessToken, userRole } = useAuthorized();
  return (
    <Suspense fallback={null}>
      <CavadaLabsDashboard
        accessToken={accessToken}
        userRole={userRole}
        initialResource={initialResource}
        initialTab={initialTab}
      />
    </Suspense>
  );
};

export default CavadaLabsRoute;
