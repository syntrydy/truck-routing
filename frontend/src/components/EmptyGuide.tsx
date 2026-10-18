/** What planning gives you, shown before the first plan, in place of an empty panel. */
export function EmptyGuide() {
  return (
    <div className="guide">
      <p className="guide__title">What you will see</p>
      <ul className="guide__list">
        <li>Up to three routes, ranked by weather risk</li>
        <li>The weather at each checkpoint, when the truck gets there</li>
        <li>A forecast for the next 48 hours along the way</li>
      </ul>
    </div>
  );
}
