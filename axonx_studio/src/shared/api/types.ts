export interface ApiResponse<T> {
  answer: T;
  success: boolean;
  metadata: Record<string, unknown>;
}
