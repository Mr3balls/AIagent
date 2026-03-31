interface StateMessageProps {
    title: string;
    description?: string;
    tone?: "default" | "success" | "warning" | "danger";
  }
  
  export function StateMessage({ title, description, tone = "default" }: StateMessageProps) {
    return (
      <div className={`state-message tone-${tone}`}>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
    );
  }