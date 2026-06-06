export type ApiResult<T> = {
  data: T;
  message?: string;
};

export type ReadinessState = 'not_built' | 'gates_running' | 'technical_ready' | 'market_blocked' | 'market_ready';
