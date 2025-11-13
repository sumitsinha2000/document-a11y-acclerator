export function formatTimeEstimate(value) {
  const minutes = Number(value);

  if (!Number.isFinite(minutes) || minutes <= 0) {
    return 'N/A';
  }

  const roundedMinutes = Math.round(minutes);
  const hours = Math.floor(roundedMinutes / 60);
  const remainingMinutes = roundedMinutes % 60;

  if (hours === 0) {
    return `${roundedMinutes} min`;
  }

  const hourLabel = hours === 1 ? 'hr' : 'hrs';

  if (remainingMinutes === 0) {
    return `${hours} ${hourLabel}`;
  }

  return `${hours} ${hourLabel} ${remainingMinutes} min`;
}
