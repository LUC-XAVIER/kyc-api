// Karma config exists for one reason: a headless-Chrome launcher that runs
// without the sandbox. CI runners (and any containerised run) execute Chrome
// in an environment where the sandbox cannot initialise, so plain
// ChromeHeadless aborts before a single test runs. Local `ng test` is
// unaffected — it keeps using the default browser unless CI asks for this one.
module.exports = function (config) {
  config.set({
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    reporters: ['progress'],
    browsers: ['Chrome'],
    restartOnFileChange: true,
    customLaunchers: {
      ChromeHeadlessNoSandbox: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox', '--disable-gpu'],
      },
    },
  });
};
