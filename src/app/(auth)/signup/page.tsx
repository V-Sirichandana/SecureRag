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
import { PasswordStrength } from "@/components/auth/password-strength";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { signup } from "@/lib/api/auth";
import { useAuthStore, useUIStore } from "@/stores/ui";
import { toast } from "sonner";

const signupSchema = z
  .object({
    name: z.string().min(2, "Enter your full name"),
    email: z.email("Enter a valid work email address"),
    organizationName: z.string().min(2, "Enter your organization name"),
    password: z
      .string()
      .min(12, "Use at least 12 characters")
      .regex(/[A-Z]/, "Include an uppercase letter")
      .regex(/[a-z]/, "Include a lowercase letter")
      .regex(/\d/, "Include a number"),
    confirmPassword: z.string(),
    terms: z.boolean().refine((value) => value === true, {
      message: "You must accept the terms to continue",
    }),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type SignupForm = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const router = useRouter();
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [oauthPending, setOauthPending] = React.useState<"google" | "github" | null>(null);
  const authLogin = useAuthStore((state) => state.login);

  const form = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      name: "",
      email: "",
      organizationName: "",
      password: "",
      confirmPassword: "",
      terms: false,
    },
    mode: "onTouched",
  });

  const { handleSubmit, register, formState, setValue, watch } = form;
  const submitting = formState.isSubmitting;
  const terms = watch("terms");
  const password = watch("password");

  const onSubmit = async (values: SignupForm) => {
    setServerError(null);
    try {
      const session = await signup({
        name: values.name,
        email: values.email,
        password: values.password,
        organizationName: values.organizationName,
      });
      authLogin(session.user, session.organizations);
      useUIStore.getState().setActiveOrganization(session.user.organizationId);
      toast.success(`Workspace â€œ${values.organizationName}â€ created.`);
      router.replace("/app/dashboard");
    } catch (error) {
      setServerError(error instanceof Error ? error.message : "Unable to create account.");
    }
  };

  const onOauth = (provider: "google" | "github") => {
    setOauthPending(provider);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    window.location.href = `${apiUrl}/api/v1/auth/oauth/${provider}`;
  };

  const fieldError = (name: keyof SignupForm) =>
    formState.errors[name]?.message as string | undefined;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight">Create your workspace</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Start with a secure, isolated knowledge base for your organization.
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
          <Label htmlFor="name">Full name</Label>
          <Input id="name" autoComplete="name" placeholder="Vishvendra Vadla" {...register("name")} />
          {fieldError("name") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("name")}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="signup-email">Work email</Label>
          <Input
            id="signup-email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            {...register("email")}
          />
          {fieldError("email") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("email")}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="org">Organization name</Label>
          <Input id="org" placeholder="Acme Technologies" {...register("organizationName")} />
          {fieldError("organizationName") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("organizationName")}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="signup-password">Password</Label>
          <PasswordInput
            id="signup-password"
            autoComplete="new-password"
            placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
            {...register("password")}
          />
          <PasswordStrength password={password ?? ""} />
          {fieldError("password") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("password")}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirm-password">Confirm password</Label>
          <PasswordInput
            id="confirm-password"
            autoComplete="new-password"
            placeholder="â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢"
            {...register("confirmPassword")}
          />
          {fieldError("confirmPassword") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("confirmPassword")}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-start gap-2.5">
            <Checkbox
              id="terms"
              className="mt-0.5"
              checked={terms}
              onCheckedChange={(checked) => setValue("terms", checked === true, { shouldValidate: true })}
            />
            <Label htmlFor="terms" className="text-sm font-normal leading-snug text-muted-foreground">
              I agree to the{" "}
              <Link href="/login" className="font-medium text-primary hover:underline">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/login" className="font-medium text-primary hover:underline">
                Privacy Policy
              </Link>
              .
            </Label>
          </div>
          {fieldError("terms") ? (
            <p className="text-xs font-medium text-destructive" role="alert">
              {fieldError("terms")}
            </p>
          ) : null}
        </div>

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating workspaceâ€¦
            </>
          ) : (
            <>
              Create account
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </form>

      <OAuthButtons onSelect={onOauth} pending={oauthPending} />

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
