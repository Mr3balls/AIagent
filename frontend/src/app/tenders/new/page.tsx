"use client";

import { ProtectedRoute } from "@/components/ProtectedRoute";
import { TenderForm } from "@/components/TenderForm";

export default function NewTenderPage() {
  return (
    <ProtectedRoute>
      <TenderForm />
    </ProtectedRoute>
  );
}