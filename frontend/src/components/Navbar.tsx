"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="navbar">
      <div className="container navbar-inner">
        <Link href={isAuthenticated ? "/dashboard" : "/login"} className="navbar-brand">
          Tender AI Frontend
        </Link>

        <nav className="navbar-links">
          {isAuthenticated ? (
            <>
              <Link href="/dashboard" className={pathname === "/dashboard" ? "active" : ""}>
                Dashboard
              </Link>
              <Link href="/tenders" className={pathname.startsWith("/tenders") && pathname !== "/tenders/new" ? "active" : ""}>
                Tenders
              </Link>
              <Link href="/tenders/new" className={pathname === "/tenders/new" ? "active" : ""}>
                New Tender
              </Link>
              <Link href="/profile" className={pathname === "/profile" ? "active" : ""}>
                Profile
              </Link>
              <button type="button" className="button button-secondary" onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className={pathname === "/login" ? "active" : ""}>
                Login
              </Link>
              <Link href="/register" className={pathname === "/register" ? "active" : ""}>
                Register
              </Link>
            </>
          )}
        </nav>

        {isAuthenticated && user ? <div className="navbar-user">{user.full_name}</div> : null}
      </div>
    </header>
  );
}