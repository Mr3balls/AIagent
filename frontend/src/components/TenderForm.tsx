"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { createTender } from "@/lib/api";
import { extractErrorMessage } from "@/lib/utils";

export function TenderForm() {
  const router = useRouter();
  const { token } = useAuth();

  const [title, setTitle] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!token) {
      setError("User is not authenticated");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const tender = await createTender(
        {
          title,
          customer_name: customerName,
          description,
        },
        token,
      );

      router.push(`/tenders/${tender.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card form-card">
      <h1>Create Tender</h1>
      <p className="muted">Create a new tender entry, then upload documents and start AI analysis.</p>

      <form className="form" onSubmit={handleSubmit}>
        <label className="form-field">
          <span>Title</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Tender title" required />
        </label>

        <label className="form-field">
          <span>Customer name</span>
          <input
            value={customerName}
            onChange={(event) => setCustomerName(event.target.value)}
            placeholder="Customer organization"
            required
          />
        </label>

        <label className="form-field">
          <span>Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Short description of procurement and scope"
            rows={6}
            required
          />
        </label>

        {error ? <div className="alert alert-error">{error}</div> : null}

        <button type="submit" className="button" disabled={loading}>
          {loading ? "Creating..." : "Create Tender"}
        </button>
      </form>
    </div>
  );
}