import '../styles/components/StructuredMessage.css'

/**
 * Rail — vertical dotted timeline connecting stops.
 * Each Stop has a time chip (mono font, navy bg), name, and description.
 */
function Stop({ stop }) {
  return (
    <div className="rail__stop">
      <div className="rail__dot-col">
        <span className="rail__dot" />
      </div>
      <div className="rail__stop-content">
        {stop.time && (
          <span className="rail__time-chip">{stop.time}</span>
        )}
        <span className="rail__stop-name">{stop.name}</span>
        {stop.desc && (
          <p className="rail__stop-desc">{stop.desc}</p>
        )}
      </div>
    </div>
  )
}

function Rail({ stops }) {
  if (!stops || stops.length === 0) return null

  return (
    <div className="rail">
      {stops.map((stop, idx) => (
        <Stop key={`${stop.time}-${idx}`} stop={stop} />
      ))}
    </div>
  )
}

export default Rail
