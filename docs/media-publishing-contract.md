# Media Publishing Contract

## Official workflow findings

YouTube’s official desktop guidance says upload begins in YouTube Studio through **Create → Upload videos**, followed by selecting the local file and editing details. YouTube notes that visibility settings determine whether the video is private, unlisted, or public, and that closing before choosing visibility leaves the upload private. Source: https://support.google.com/youtube/answer/57407?hl=en&co=GENIE.Platform%3DDesktop

Instagram’s official computer help guidance describes creating a post, selecting media from the computer, continuing through the next steps, adding caption and settings, and selecting **Share**. Source: https://help.instagram.com/2720958398006062/

## Adapter contract

The workflow must locate the newest supported local video under an allowed root, open the user’s existing browser session, navigate to the provider upload page, select the file using a Playwright file chooser/input, fill bounded ordinary metadata, and return a review summary. It must pause when a login wall, CAPTCHA, MFA prompt, copyright warning, account restriction, or unexpected page state is detected. Each final Share/Publish action is a separate sensitive dispatcher operation requiring immediate user confirmation.

Raw passwords, tokens, OTP values, and CAPTCHA data must never enter the model prompt, chat history, audit output, or backup archive. The adapter may use an already-authenticated browser session but must not extract cookies or credentials. Provider selectors are configurable and validated; arbitrary JavaScript, hidden downloads, and automatic CAPTCHA solving are prohibited.
