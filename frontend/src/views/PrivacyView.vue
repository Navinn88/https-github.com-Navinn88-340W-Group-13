<script setup lang="ts">
import ArrowLeftIcon from '@/components/icons/ArrowLeftIcon.vue'
</script>

<template>
  <div
    class="min-h-screen flex flex-col justify-center relative overflow-hidden px-6 bg-white dark:bg-gray-900"
  >
    <div class="mx-auto w-full px-6 py-12 max-w-3xl">
      <RouterLink
        :to="{ name: 'home' }"
        :class="'flex text-gray-500 transition-colors duration-200 hover:text-gray-700 dark:text-gray-400 dark:hover:text-white'"
        ><ArrowLeftIcon class="w-6 h-6 mr-1" />Back to CIRA</RouterLink
      >
      <div class="mt-6 prose prose-gray dark:prose-invert lg:prose-base !max-w-none">
        <h2>CIRA Data Collection and Usage</h2>
        <p>
          This is a chatbot designed to assist canvas users at Penn State with information
          retrieval.
        </p>
        <h3>Voluntary Participation</h3>
        <p>
          Interaction with CIRA is completely voluntary, and can be stopped by closing the chatbot
          window.
        </p>
        <h3>Confidentiality</h3>
        <p>
          Your conversations will be kept confidential. All data will be stored securely on the
          digital infrastructure of Marburg University. Only the research team and system
          administrators will have access to it. If the results of this research are published, it
          will be in an aggregated form and will not contain any personally identifying information.
          You will remain completely anonymous.
        </p>

        <h3>Collection and Use of Data</h3>
        <p>
          The data collected will only be used for academic research. This includes analyzing the
          helpfulness of chatbot responses to identify areas for improvement. The results may be
          disseminated in an aggregated manner through academic publications. The data will be
          completely anonymized and we won't be able to trace conversations back to you. There is no
          need to provide any personal information in conversations, such as your name, email or
          student ID, and we recommend that you do not do so.
        </p>
        <p>
          We do not use or process any cookies from third parties. Further data processing including
          access logs (e.g., IP addresses and user agents) follow the data protection standards of
          the Department of Mathematics and Computer Science of Marburg University:
          <a href="https://www.mathematik.uni-marburg.de/legal/datenschutz.html#english"
            >https://www.mathematik.uni-marburg.de/legal/datenschutz.html#english</a
          >
        </p>

        <h3>Risks and Benefits</h3>
        <p>
          There are no anticipated risks associated with participation in this study. There is a
          minimal chance of discomfort if the chatbot provides incorrect or unclear information. We
          always recommend verifying the generated answers through Canvas. If you have any doubts
          regarding a generated answer that concerns your study or study plans, leave feedback
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLScyrAgqWzKmSIrW32LVW0DKmQv2uA-bVsPvZAWYvVgbg6GFwQ/viewform?usp=publish-editor"
            target="_blank"
            >here</a
          >. By participating, you will be contributing to research that will improve the chatbot
          and access to information.
        </p>

        <h3>Withdrawal of Consent</h3>
        <p>
          You may withdraw your consent and stop using the chatbot at any time. If you would like us
          to delete any of your interaction data, please contact us using the information below.
          Include in your request the specific questions you asked and times of interaction.
        </p>

        <h3>Contact Information</h3>
        <p>
          If you have any questions about this study or the provided service, please contact us at
        </p>
        <ul>
          <li>
            <a href="mailto:tjg311@psu.edu">Tyler Gully</a>
          </li>
          <li>
            <a href="mailto:hab5455@psu.edu">Harvey Barnes</a>
          </li>
          <li>
            <a href="mailto:gld5224@psu.edu">Gavin Dunlap</a>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
