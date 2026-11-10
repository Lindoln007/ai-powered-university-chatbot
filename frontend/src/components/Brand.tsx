/** The Campus Desk mark: a speech bubble whose tail doubles as a desk corner, with a gold dot. */
export function Mark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className="mark">
      <rect width="40" height="40" rx="12" className="mark__tile" />
      <path
        d="M11 12.5h13.5a6.5 6.5 0 0 1 0 13H18l-5.2 4.3c-.7.6-1.8.1-1.8-.8z"
        className="mark__bubble"
        strokeWidth="2.6"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="28.5" cy="12.5" r="3.6" className="mark__dot" />
    </svg>
  );
}

/** Decorative backdrop for the welcome screen: a sun rising over layered hills. */
export function Horizon() {
  return (
    <svg className="horizon" viewBox="0 0 520 300" aria-hidden="true" preserveAspectRatio="xMaxYMin slice">
      <circle cx="372" cy="118" r="74" className="horizon__sun" />
      <circle cx="372" cy="118" r="108" className="horizon__ring" fill="none" strokeWidth="1.5" />
      <circle cx="372" cy="118" r="146" className="horizon__ring" fill="none" strokeWidth="1.5" strokeDasharray="2 9" />
      <path d="M0 232c70-58 138-64 214-22s150 30 306-62v152H0z" className="horizon__hill horizon__hill--far" />
      <path d="M0 268c96-52 188-50 270-14s168 22 250-26v72H0z" className="horizon__hill horizon__hill--near" />
    </svg>
  );
}
