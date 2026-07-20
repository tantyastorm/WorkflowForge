type LoadingStateProps = {
  message?: string;
};

export function LoadingState({ message = "Loading" }: LoadingStateProps) {
  return (
    <div className="feedback-state" role="status" aria-live="polite">
      <p className="feedback-state__label">{message}</p>
    </div>
  );
}
