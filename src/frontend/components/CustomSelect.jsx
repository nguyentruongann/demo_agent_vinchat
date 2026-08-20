import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import '../styles/components/CustomSelect.css'

export default function CustomSelect({
  value,
  options = [],
  onChange,
  placeholder = '',
  icon: Icon,
  className = '',
  id,
  'aria-label': ariaLabel,
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  const normalizedOptions = options.map((opt) => {
    if (typeof opt === 'object' && opt !== null) {
      return {
        value: opt.value ?? opt.id,
        label: opt.label ?? opt.name ?? String(opt.value ?? opt.id),
      }
    }
    return { value: opt, label: String(opt) }
  })

  const selected = normalizedOptions.find((opt) => String(opt.value) === String(value)) || normalizedOptions[0]

  useEffect(() => {
    function handleOutsideClick(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', handleOutsideClick)
    return () => document.removeEventListener('pointerdown', handleOutsideClick)
  }, [])

  return (
    <div
      className={`custom-select ${open ? 'custom-select--open' : ''} ${className}`}
      ref={rootRef}
      id={id}
    >
      <button
        type="button"
        className="custom-select__trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
        }}
      >
        {Icon && <Icon className="custom-select__icon" aria-hidden="true" />}
        <span className="custom-select__value">{selected ? selected.label : placeholder}</span>
        <ChevronDown className="custom-select__chevron" aria-hidden="true" />
      </button>

      {open && (
        <div className="custom-select__menu" role="listbox" aria-label={ariaLabel}>
          {normalizedOptions.map((opt) => {
            const isSelected = String(opt.value) === String(value)
            return (
              <button
                type="button"
                role="option"
                key={String(opt.value)}
                aria-selected={isSelected}
                className={`custom-select__option ${isSelected ? 'is-selected' : ''}`}
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
              >
                <span>{opt.label}</span>
                {isSelected && <Check className="custom-select__check" aria-hidden="true" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
