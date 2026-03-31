import { User } from "@/lib/types";
import { formatDate } from "@/lib/utils";

interface ProfileCardProps {
  user: User;
}

export function ProfileCard({ user }: ProfileCardProps) {
  return (
    <div className="card profile-card">
      <h1>Profile</h1>
      <div className="data-grid">
        <div>
          <span className="label">Full name</span>
          <strong>{user.full_name}</strong>
        </div>
        <div>
          <span className="label">Email</span>
          <strong>{user.email}</strong>
        </div>
        <div>
          <span className="label">Created at</span>
          <strong>{formatDate(user.created_at)}</strong>
        </div>
      </div>
    </div>
  );
}