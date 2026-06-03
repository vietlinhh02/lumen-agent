import NavBar from "@/components/NavBar";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <NavBar />
      <main className="flex flex-1 flex-col items-center justify-center px-6">
        <h1
          className="font-display text-[72px] font-bold leading-[1.0] text-ink animate-scale-in"
          style={{ letterSpacing: "-1.8px" }}
        >
          Welcome back
        </h1>
        <p className="mt-4 text-lg leading-[1.56] text-body animate-fade-in delay-300">
          Your AI literature review workspace is ready.
        </p>
      </main>
    </div>
  );
}
