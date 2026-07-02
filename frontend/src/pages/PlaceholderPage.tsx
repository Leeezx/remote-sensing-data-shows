interface PlaceholderPageProps {
  title: string
}

export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <main className="placeholder-page">
      <section className="placeholder-content">
        <h2>{title}</h2>
        <p>该板块暂未实现。</p>
      </section>
    </main>
  )
}
