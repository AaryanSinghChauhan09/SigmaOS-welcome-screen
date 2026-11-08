//! SigmaOS-welcome-screen — First-boot welcome wizard for SigmaOS.

/// Onboarding step
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum OnboardingStep {
    #[default]
    Welcome,
    LanguageSelection,
    ThemeSelection,
    DriverSetup,
    UserAccount,
    NetworkSetup,
    Completed,
}

/// Wizard state
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WizardState {
    /// Not started
    Idle,
    /// In progress
    Running,
    /// Completed
    Completed,
    /// Skipped
    Skipped,
}

/// Welcome wizard
#[derive(Debug, Clone)]
pub struct WelcomeWizard {
    current_step: OnboardingStep,
    state: WizardState,
    selected_language: Option<String>,
    selected_theme: Option<String>,
    username: Option<String>,
    hostname: Option<String>,
    steps_completed: usize,
}

impl Default for WelcomeWizard {
    fn default() -> Self { Self::new() }
}

impl WelcomeWizard {
    /// Create new wizard
    pub fn new() -> Self {
        Self {
            current_step: OnboardingStep::Welcome,
            state: WizardState::Idle,
            selected_language: None,
            selected_theme: None,
            username: None,
            hostname: None,
            steps_completed: 0,
        }
    }

    /// Start wizard
    pub fn start(&mut self) {
        self.state = WizardState::Running;
        self.current_step = OnboardingStep::Welcome;
    }

    /// Advance to next step
    pub fn next_step(&mut self) {
        if self.state != WizardState::Running { return; }
        self.current_step = match self.current_step {
            OnboardingStep::Welcome => OnboardingStep::LanguageSelection,
            OnboardingStep::LanguageSelection => OnboardingStep::ThemeSelection,
            OnboardingStep::ThemeSelection => OnboardingStep::DriverSetup,
            OnboardingStep::DriverSetup => OnboardingStep::UserAccount,
            OnboardingStep::UserAccount => OnboardingStep::NetworkSetup,
            OnboardingStep::NetworkSetup => OnboardingStep::Completed,
            OnboardingStep::Completed => OnboardingStep::Completed,
        };
        if self.current_step == OnboardingStep::Completed {
            self.state = WizardState::Completed;
        } else {
            self.steps_completed += 1;
        }
    }

    /// Skip current step
    pub fn skip_step(&mut self) {
        self.next_step();
    }

    /// Select language
    pub fn select_language(&mut self, lang: &str) {
        self.selected_language = Some(lang.into());
    }

    /// Select theme
    pub fn select_theme(&mut self, theme: &str) {
        self.selected_theme = Some(theme.into());
    }

    /// Set username
    pub fn set_username(&mut self, username: &str) {
        self.username = Some(username.into());
    }

    /// Set hostname
    pub fn set_hostname(&mut self, hostname: &str) {
        self.hostname = Some(hostname.into());
    }

    /// Check if completed
    pub fn is_completed(&self) -> bool {
        self.current_step == OnboardingStep::Completed || self.state == WizardState::Completed
    }

    /// Get current step
    pub fn current_step(&self) -> OnboardingStep { self.current_step }

    /// Get state
    pub fn state(&self) -> &WizardState { &self.state }

    /// Get steps completed count
    pub fn steps_completed(&self) -> usize { self.steps_completed }

    /// Get selected language
    pub fn selected_language(&self) -> Option<&str> {
        self.selected_language.as_deref()
    }

    /// Get selected theme
    pub fn selected_theme(&self) -> Option<&str> {
        self.selected_theme.as_deref()
    }

    /// Get username
    pub fn username(&self) -> Option<&str> {
        self.username.as_deref()
    }

    /// Get hostname
    pub fn hostname(&self) -> Option<&str> {
        self.hostname.as_deref()
    }

    /// Reset wizard
    pub fn reset(&mut self) {
        *self = Self::new();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_step_order() {
        let steps = vec![
            OnboardingStep::Welcome,
            OnboardingStep::LanguageSelection,
            OnboardingStep::ThemeSelection,
            OnboardingStep::DriverSetup,
            OnboardingStep::UserAccount,
            OnboardingStep::NetworkSetup,
            OnboardingStep::Completed,
        ];
        assert_eq!(steps.len(), 7);
    }

    #[test]
    fn test_wizard_progression() {
        let mut wiz = WelcomeWizard::new();
        assert_eq!(wiz.current_step(), OnboardingStep::Welcome);
        assert_eq!(wiz.state(), &WizardState::Idle);
        
        wiz.start();
        assert_eq!(wiz.state(), &WizardState::Running);
        
        wiz.next_step();
        assert_eq!(wiz.current_step(), OnboardingStep::LanguageSelection);
        
        // Complete all steps
        for _ in 0..6 {
            wiz.next_step();
        }
        assert!(wiz.is_completed());
        assert_eq!(wiz.state(), &WizardState::Completed);
    }

    #[test]
    fn test_wizard_selections() {
        let mut wiz = WelcomeWizard::new();
        wiz.select_language("en_US");
        wiz.select_theme("dracula");
        wiz.set_username("alice");
        wiz.set_hostname("sigmaos");
        
        assert_eq!(wiz.selected_language(), Some("en_US"));
        assert_eq!(wiz.selected_theme(), Some("dracula"));
        assert_eq!(wiz.username(), Some("alice"));
        assert_eq!(wiz.hostname(), Some("sigmaos"));
    }

    #[test]
    fn test_wizard_skip() {
        let mut wiz = WelcomeWizard::new();
        wiz.start();
        wiz.skip_step();
        assert_eq!(wiz.current_step(), OnboardingStep::LanguageSelection);
    }

    #[test]
    fn test_wizard_reset() {
        let mut wiz = WelcomeWizard::new();
        wiz.start();
        wiz.next_step();
        wiz.select_language("fr_FR");
        
        wiz.reset();
        assert_eq!(wiz.current_step(), OnboardingStep::Welcome);
        assert_eq!(wiz.state(), &WizardState::Idle);
        assert_eq!(wiz.selected_language(), None);
    }

    #[test]
    fn test_steps_completed_count() {
        let mut wiz = WelcomeWizard::new();
        wiz.start();
        assert_eq!(wiz.steps_completed(), 0);
        
        wiz.next_step();
        assert_eq!(wiz.steps_completed(), 1);
        
        wiz.next_step();
        assert_eq!(wiz.steps_completed(), 2);
    }

    #[test]
    fn test_next_step_when_idle() {
        let mut wiz = WelcomeWizard::new();
        // next_step does nothing when not running
        wiz.next_step();
        assert_eq!(wiz.current_step(), OnboardingStep::Welcome);
    }

    #[test]
    fn test_full_onboarding_flow() {
        let mut wiz = WelcomeWizard::new();
        wiz.start();
        
        // Welcome -> Language
        wiz.select_language("de_DE");
        wiz.next_step();
        
        // Language -> Theme
        wiz.select_theme("nord");
        wiz.next_step();
        
        // Theme -> Driver
        wiz.next_step();
        
        // Driver -> User
        wiz.set_username("bob");
        wiz.set_hostname("workstation");
        wiz.next_step();
        
        // User -> Network
        wiz.next_step();
        
        // Network -> Completed
        wiz.next_step();
        
        assert!(wiz.is_completed());
        assert_eq!(wiz.selected_language(), Some("de_DE"));
        assert_eq!(wiz.selected_theme(), Some("nord"));
        assert_eq!(wiz.username(), Some("bob"));
        assert_eq!(wiz.hostname(), Some("workstation"));
    }
}
