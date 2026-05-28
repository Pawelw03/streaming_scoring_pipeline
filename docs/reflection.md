# What part of the task was hardest, and why?
- The hardest was to understand new concepts. Many of them were either completely new to me, or at least I've never worked on implementing them. Because of that the hardest part was the beginning and building basic feature_builder and scoring funcionality. Even with help of AI, having big chunks of code prepared, I couldn't say right away if it actually covers concepts required by the task. Once I had understanding of the core elements of the system, implementing next feautures was much easier.
Learning through concepts was the most time consuming part. I didn't find time to work on tests and setting up git hub - I'll probably still work on it after submission to practice. Likely I will also anyway setup this or similar project on actual infrastracture at least to practice these concepts.

# What would you redesign for a real production system?
- I've included in architecture md also patterns I would use in production for many elements. Generally I would probably deploy it using AWS services.
- Model training would be separated from scoring.
    - It could be run manually and/or set as separate workflow run periodically and producing new model version.
    - New model version would be published externally (eg. on S3). I wouldn't include artifacts in the docker image.
- Scoring service would download latest (or selected/pointed/active) model from S3.
- Replay strategy.
    - This simulation uses `self.state` which causes new state creation when new instance of the script is initialized.
    - ??? In production we would use persistent storage (state carried across sessions)
- I would add retry loop for the optimistic locking. currently state only holds and updates version number. In case there is version conflict because of concurrent processing event with mismatching expected version have to be re-processed.
- I would think about splitting functionalities into smaller modules and probably refactoring some of them.
- For replaying state I would think of limiting starting point (to not go through whole history while we only asses 30 days). Not sure if it would be needed.
- I would add some scaling options to enable concurrent processing.
- I would implement tests.

# What assumptions did you make that could be wrong?
- Storing all events in single document per customer can cause exceeding 400KB limit for dynamoDB document.
- 30 days window is calculated from the latest event per customer. It seems to be reasonable but I can imagine different windowing, eg, from current time.

# What trade-offs did you consciously accept?
- Simplicity - I aimed for minimal setup needed to meet the requirements. Still in many cases I have impression I've added more than needed.
- Model cannot learn on newly arriving data instantly. Training is done in batches. From one hand model can be sometimes outdated with such approach, but at the same time it makes the training less susceptible to data issues. Definitely batch is easier to implement so it's also a benefit.
- We drop events older than 30 days to limit data stored in DynamoDB. Normally longer history could be still availble in S3 though. (later I've added state.json to actually store all events, still normally it would be S3)
