"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import CavadaLabsDashboard from "@/components/cavadalabs/CavadaLabsDashboard";
import { Suspense } from "react";

const CavadaLabsPage = () => {
  const { accessToken, userRole } = useAuthorized();
  return (
    <Suspense fallback={null}>
      <CavadaLabsDashboard accessToken={accessToken} userRole={userRole} />
    </Suspense>
  );
};

export default CavadaLabsPage;
