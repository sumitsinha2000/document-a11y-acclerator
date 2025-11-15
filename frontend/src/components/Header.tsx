
const Header: React.FC = () => {
  return (
    <header className="bg-transparent backdrop-blur-sm sticky top-0 z-10 border-b border-gray-200">
      <div className="container mx-auto p-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800 tracking-tight">
          A11y <span className="text-indigo-600">Remediation Hub</span>
        </h1>
      </div>
    </header>
  );
};

export default Header;