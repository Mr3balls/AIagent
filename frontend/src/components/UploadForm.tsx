"use client";

import { FormEvent, useRef, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { uploadTenderDocuments } from "@/lib/api";
import { extractErrorMessage } from "@/lib/utils";

interface UploadFormProps {
  tenderId: string;
  onUploaded: () => Promise<unknown> | void;
}

export function UploadForm({ tenderId, onUploaded }: UploadFormProps) {
  const { token } = useAuth();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!token) {
      setError("User is not authenticated");
      return;
    }

    if (files.length === 0) {
      setError("Please select at least one document");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await uploadTenderDocuments(tenderId, files, token);
      setSuccess("Documents uploaded successfully.");
      setFiles([]);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      await onUploaded();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card form-card">
      <h2>Upload Documents</h2>
      <p className="muted">Supported formats: PDF, DOCX, XLSX. Files are sent as multipart form-data under the key files.</p>

      <form className="form" onSubmit={handleSubmit}>
        <label className="form-field">
          <span>Select files</span>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.xls,.xlsx"
            onChange={(event) => setFiles(Array.from(event.target.files || []))}
          />
        </label>

        {files.length > 0 ? (
          <div className="file-list">
            {files.map((file) => (
              <div key={`${file.name}-${file.size}`} className="file-list-item">
                <span>{file.name}</span>
                <span className="muted">{Math.round(file.size / 1024)} KB</span>
              </div>
            ))}
          </div>
        ) : null}

        {error ? <div className="alert alert-error">{error}</div> : null}
        {success ? <div className="alert alert-success">{success}</div> : null}

        <button type="submit" className="button" disabled={loading}>
          {loading ? "Uploading..." : "Upload Documents"}
        </button>
      </form>
    </div>
  );
}