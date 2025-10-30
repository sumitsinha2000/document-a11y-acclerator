export function formatTimeEstimate(minutes) {
  if (!minutes || isNaN(minutes)) return 'N/A';

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours === 0) {
    return `${minutes} min`;
  }

  return `${hours}:${remainingMinutes.toString().padStart(2, '0')} hours`;
}
