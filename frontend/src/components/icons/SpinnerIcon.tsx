
export const SpinnerIcon: React.FC<React.SVGProps<SVGSVGElement>> = (props) => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    fill="none" 
    viewBox="0 0 24 24"
    strokeWidth={2} 
    stroke="currentColor" 
    className="animate-spin"
    {...props}
  >
    <path 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      d="M12 3v3m0 12v3m9-9h-3M6 12H3m16.5-6.5l-2.12 2.12M7.62 16.38l-2.12 2.12M16.38 7.62l2.12-2.12M5.5 5.5l2.12 2.12" 
      stroke="url(#spinner-gradient)"
    />
     <defs>
      <linearGradient id="spinner-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style={{stopColor: 'rgb(79 70 229)', stopOpacity:1}} />
        <stop offset="100%" style={{stopColor: 'rgb(209 213 219)', stopOpacity:0}} />
      </linearGradient>
    </defs>
  </svg>
);