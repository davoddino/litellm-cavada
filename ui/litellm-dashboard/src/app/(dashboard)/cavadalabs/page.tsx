"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import CavadaLabsDashboard from "@/components/cavadalabs/CavadaLabsDashboard";

const CavadaLabsPage = () => {
  const { accessToken, userRole } = useAuthorized();
  return <CavadaLabsDashboard accessToken={accessToken} userRole={userRole} />;
};

export default CavadaLabsPage;
