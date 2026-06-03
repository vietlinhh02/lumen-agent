import BrandPanel from "@/components/BrandPanel";
import LoginForm from "@/components/LoginForm";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen">
      <BrandPanel />
      <div className="flex flex-1 flex-col items-center justify-center bg-canvas px-6 lg:px-16">
        <LoginForm />
      </div>
    </div>
  );
}
