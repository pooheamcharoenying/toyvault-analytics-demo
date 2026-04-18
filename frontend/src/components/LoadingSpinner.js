export default function LoadingSpinner({ message = "Loading data..." }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-slate-500">
      <div className="animate-spin rounded-full h-10 w-10 border-4 border-slate-200 border-t-[var(--nichi-blue)] mb-4"></div>
      <p className="text-sm">{message}</p>
    </div>
  );
}
