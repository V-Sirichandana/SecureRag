"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertCircle, ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PasswordInput } from "@/components/auth/password-input";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { login } from "@/lib/api/auth";
import { useAuthStore, useUIStore } from "@/stores/ui";
import { toast } from "sonner";

const loginSchema = z.object({
  email: z.email("Enter a valid work email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
  remember: z.boolean(),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [oauthPending, setOauthPending] = React.useState<"google" | "github" | null>(null);
  const authLogin = useAuthStore((state) => state.login);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "vishvendra@acmetech.io", password: "SecureRAG!2026", remember: true },
  });

  const { handleSubmit, register, formState, setValue, watch } = form;
  const submitting = formState.isSubmitting;
  const remember = watch("remember");

  const onSubmit = async (values: LoginForm) => {
    setServerError(null);
    try {
      const session = await login(values);
      authLogin(session.user, session.organizations);
      useUIStore.getState().setActiveOrganization(session.user.organizationId);
      toast.success("Welcome back to SecureRAG.");
      router.replace("/app/dashboard");
    } catch (error) {
      setServerError(error instanceof Error ? error.message : "Unable to sign in.");
    }
  };

  const onOauth = (provider: "google" | "github") => {
    setServerError(null);
    setOauthPending(provider);
    // Redirect the browser to the backend OAuth start endpoint, which redirects
    // to the provider and ultimately back to /app/dashboard with a session.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    window.location.href = `${apiUrl}/api/v1/auth/oauth/${provider}`;
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Sign in to your workspace</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Use your organization credentials to access the knowledge base.
        </p>
      </div>

      {serverError ? (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="email">Work email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            aria-invalid={Boolean(formState.errors.email)}
            {...register("email")}
          />
          {formState.errors.email ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {formState.errors.email.message}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link
              href="/forgot-password"
              className="text-xs font-medium text-primary hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder="••••••••••••"
            aria-invalid={Boolean(formState.errors.password)}
            {...register("password")}
          />
          {formState.errors.password ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {formState.errors.password.message}
            </p>
          ) : null}
        </div>

        <div className="flex items-center gap-2.5">
          <Checkbox
            id="remember"
            checked={remember}
            onCheckedChange={(checked) => setValue("remember", checked === true)}
          />
          <Label htmlFor="remember" className="text-sm font-normal text-muted-foreground">
            Keep me signed in on this device
          </Label>
        </div>

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Signing in…
            </>
          ) : (
            <>
              Sign in
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </form>

      <OAuthButtons onSelect={onOauth} pending={oauthPending} />

      <p className="mt-6 text-center text-sm text-muted-foreground">
        New to SecureRAG?{" "}
        <Link href="/signup" className="font-medium text-primary hover:underline">
          Create an account
        </Link>
      </p>
    </div>
  );
}
