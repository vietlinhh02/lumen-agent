import { LoginGuard } from "@/components/LoginGuard";
import BrandPanel from "@/components/BrandPanel";
import RegisterForm from "@/components/RegisterForm";

export default function RegisterPage() {
  return (
    <LoginGuard>
      <div className="flex min-h-screen">
        <BrandPanel />
        <div className="flex flex-1 flex-col items-center justify-center bg-canvas px-6 lg:px-16">
          <RegisterForm />
        </div>
      </div>
    </LoginGuard>
  );
}
