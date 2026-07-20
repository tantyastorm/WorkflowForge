type ErrorStateProps = {
  title: string;
  message: string;
  actionLabel?: string;
  onRetry?: () => void;
};

export function ErrorState({ title, message, actionLabel, onRetry }: ErrorStateProps) {
  return (
    <section className="feedback-state" aria-labelledby="error-state-title">
      <h1 id="error-state-title" className="feedback-state__title">
        {title}
      </h1>
      <p className="feedback-state__message">{message}</p>
      {onRetry !== undefined && actionLabel !== undefined ? (
        <button className="button" type="button" onClick={onRetry}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}
