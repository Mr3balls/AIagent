"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { StateMessage } from "@/components/StateMessage";

export default function HomePage() {
  const router = useRouter();
  const { loading, isAuthenticated } = useAuth();

  useEffect(() => {
    if (!loading) {
      router.replace(isAuthenticated ? "/dashboard" : "/login");
    }
  }, [loading, isAuthenticated, router]);

  return <StateMessage title="Redirecting" description="Opening the correct start page for your session." />;
}