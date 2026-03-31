interface SectionCardProps {
    title: string;
    children: React.ReactNode;
  }
  
  export function SectionCard({ title, children }: SectionCardProps) {
    return (
      <section className="card section-card">
        <div className="section-card-header">
          <h3>{title}</h3>
        </div>
        <div className="section-card-body">{children}</div>
      </section>
    );
  }