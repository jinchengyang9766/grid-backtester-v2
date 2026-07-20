/**
 * Request/response contracts for the authentication endpoints
 * (SPEC Section 25.1), mirroring the backend Pydantic schemas exactly.
 *
 * No token field exists anywhere in these shapes: the access token travels
 * only in the HttpOnly cookie and is never exposed to JavaScript.
 */

export interface RegisterRequest {
  email: string;
  password: string;
}

/** `POST /api/auth/register` → 201. */
export interface RegisteredUser {
  id: number;
  email: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/** `POST /api/auth/login` → 200 and `GET /api/auth/me` → 200. */
export interface AuthenticatedUser {
  id: number;
  email: string;
}
