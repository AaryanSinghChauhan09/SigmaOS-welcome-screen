#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum OnboardingStep { #[default] Welcome, ThemeSelection, DriverSetup, Completed }

#[derive(Debug, Default)]
pub struct WelcomeWizard {
    current_step: OnboardingStep,
}

impl WelcomeWizard {
    pub fn new() -> Self { Self { current_step: OnboardingStep::Welcome } }
    pub fn next_step(&mut self) {
        self.current_step = match self.current_step {
            OnboardingStep::Welcome => OnboardingStep::ThemeSelection,
            OnboardingStep::ThemeSelection => OnboardingStep::DriverSetup,
            _ => OnboardingStep::Completed,
        };
    }
    pub fn is_completed(&self) -> bool { self.current_step == OnboardingStep::Completed }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_welcome_wizard_progression() {
        let mut wiz = WelcomeWizard::new();
        assert!(!wiz.is_completed());
        wiz.next_step();
        wiz.next_step();
        wiz.next_step();
        assert!(wiz.is_completed());
    }
}
